import json
import os
import re
import subprocess
import time
import uuid

import requests
import runpod
import soundfile as sf

from yue2 import YuE2Pipeline


MODEL_ID = os.getenv("YUE_MODEL", "m-a-p/YuE2-3B")
VAE_ID = os.getenv("YUE_VAE", "m-a-p/YuE2-Vae")
LEGACY_VAE_ID = os.getenv("YUE_VAE_LEGACY", "m-a-p/YuE2-Vae-legacy")
UPLOAD_URL = os.getenv("ARTIFACT_UPLOAD_URL", "").strip()
UPLOAD_TOKEN = os.getenv("ARTIFACT_UPLOAD_TOKEN", "").strip()

GENERATE_NAMES = (
    "audio.flac",
    "score.abc",
    "plan.json",
    "result.json",
    "config.json",
    "request.json",
)
PLAN_NAMES = (
    "request.json",
    "score.abc",
    "plan.json",
    "plan_manifest.json",
    "abc_tokens.npy",
    "prefix.npy",
)
EXTRA_NAMES = (
    "audio-standard.flac",
    "audio-legacy.flac",
    "audio.mp3",
    "audio.wav",
    "loudness.json",
)

print("Loading YuE2...")

pipe = YuE2Pipeline.from_pretrained(
    MODEL_ID,
    vae=VAE_ID,
    device="cuda",
)

print("YuE2 loaded.")


def upload_artifacts(output_dir, generation_id, names):
    """Hand artifacts to the studio before this ephemeral worker goes away.

    Serverless workers may terminate right after the request, so files in
    /tmp are not durable. When ARTIFACT_UPLOAD_URL is configured the handler
    POSTs them to the application, which stores them persistently and serves
    them to the player. The handoff never fails the generation.
    """
    if not UPLOAD_URL:
        return {
            "artifacts_uploaded": False,
            "upload_skipped": "ARTIFACT_UPLOAD_URL is not configured",
        }

    handles = []
    try:
        files = {"generation_id": (None, generation_id)}
        for name in names:
            path = os.path.join(output_dir, name)
            if os.path.isfile(path):
                handle = open(path, "rb")
                handles.append(handle)
                files[name] = (name, handle, "application/octet-stream")
        headers = (
            {"Authorization": f"Bearer {UPLOAD_TOKEN}"} if UPLOAD_TOKEN else {}
        )
        response = requests.post(
            UPLOAD_URL, files=files, headers=headers, timeout=600
        )
        return {
            "artifacts_uploaded": response.ok,
            "upload_status": response.status_code,
        }
    except Exception as exc:  # noqa: BLE001 - never fail the song for this
        return {"artifacts_uploaded": False, "upload_error": str(exc)[:300]}
    finally:
        for handle in handles:
            handle.close()


def build_request(data):
    request = {
        "id": data.get("id", str(uuid.uuid4())),
        "style": data.get("style"),
        "lyrics": data.get("lyrics"),
        "cot": data.get("cot", "full"),
        "seed": int(data.get("seed", 42)),
    }

    # External composition (cover workflow) and text guidance are part of the
    # SongRequest protocol; pass them through when provided. SongRequest itself
    # validates the rules (abc requires cot=full|melody, cfg_scale in [0,20]).
    abc = data.get("abc")
    if isinstance(abc, str) and abc.strip():
        request["abc"] = abc

    cfg_scale = data.get("cfg_scale")
    if cfg_scale is not None:
        request["cfg_scale"] = float(cfg_scale)

    return request


def build_sampling(data):
    sampling_kwargs = {}
    abc_sampling = data.get("abc_sampling")
    if isinstance(abc_sampling, dict) and abc_sampling:
        sampling_kwargs["abc_sampling"] = abc_sampling
    semantic_sampling = data.get("semantic_sampling")
    if isinstance(semantic_sampling, dict) and semantic_sampling:
        sampling_kwargs["semantic_sampling"] = semantic_sampling
    return sampling_kwargs


def normalize_bpm(value):
    if value is None:
        return None
    match = re.search(r"\d+(?:\.\d+)?", str(value))
    if not match:
        return None
    bpm = int(round(float(match.group(0))))
    return bpm if 20 <= bpm <= 300 else None


def set_abc_tempo(text, bpm):
    """Rewrite (or insert) the Q: tempo header. Mirrors the studio's tool."""
    header = f"Q:1/4={bpm}"
    if re.search(r"^Q:.*$", text, flags=re.M):
        return re.sub(r"^Q:.*$", header, text, count=1, flags=re.M)
    lines = text.split("\n")
    index = next(
        (i for i, line in enumerate(lines) if line.strip().startswith("K:")),
        None,
    )
    lines.insert(index if index is not None else len(lines), header)
    return "\n".join(lines)


def plan_with_bpm(request, sampling_kwargs, bpm):
    """Plan the score and, when the caller asked for a tempo, enforce it.

    Style text only hints at a BPM; the model picks its own Q: otherwise
    (measured live: "60 bpm" style produced Q:1/4=70). The adjusted ABC is
    then used as the external composition so the semantic stage - and the
    saved artifacts - follow the requested tempo. An ABC supplied by the
    caller is authoritative and never touched.
    """
    # plan() defines abc_sampling explicitly; semantic_sampling would land in
    # **kwargs and blow up SongRequest.__init__.
    plan_kwargs = {
        key: value for key, value in sampling_kwargs.items() if key == "abc_sampling"
    }
    plan = pipe.plan(**request, **plan_kwargs)
    if not bpm or request.get("abc") or not plan.abc:
        return plan
    adjusted = set_abc_tempo(plan.abc, bpm)
    if adjusted == plan.abc:
        return plan
    return pipe.plan(**{**request, "abc": adjusted}, **plan_kwargs)


def run_ffmpeg(args):
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args],
        check=True,
        capture_output=True,
        timeout=900,
    )


def convert_formats(output_dir, formats):
    results = {}
    source = os.path.join(output_dir, "audio.flac")
    if not os.path.isfile(source):
        return results
    for fmt in formats:
        target = os.path.join(output_dir, f"audio.{fmt}")
        try:
            if fmt == "mp3":
                run_ffmpeg(["-i", source, "-codec:a", "libmp3lame", "-b:a", "320k", target])
            elif fmt == "wav":
                run_ffmpeg(["-i", source, "-c:a", "pcm_s24le", target])
            else:
                continue
            results[fmt] = os.path.isfile(target)
        except Exception as exc:  # noqa: BLE001 - delivery extra, never fatal
            results[fmt] = f"failed: {str(exc)[:200]}"
    return results


def measure_loudness(output_dir):
    source = os.path.join(output_dir, "audio.flac")
    if not os.path.isfile(source):
        return {"error": "audio.flac not found"}
    process = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-i",
            source,
            "-filter_complex",
            "ebur128=peak=true",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        timeout=900,
    )
    report = process.stderr

    # ebur128 streams per-frame progress lines; "I:" appears there from the
    # very first silent frame (I: -70 LUFS). The authoritative values are in
    # the final Summary block, so parse from the last "Summary:" onward.
    summary_index = report.rfind("Summary:")
    section = report[summary_index:] if summary_index >= 0 else report

    def grab(pattern):
        match = re.search(pattern, section)
        return float(match.group(1)) if match else None

    data = {
        "integrated_lufs": grab(r"I:\s*(-?\d+(?:\.\d+)?)\s*LUFS"),
        "loudness_range_lu": grab(r"LRA:\s*(-?\d+(?:\.\d+)?)\s*LU"),
        "true_peak_dbfs": grab(r"Peak:\s*(-?\d+(?:\.\d+)?)\s*dBFS"),
        "source": "ffmpeg ebur128 (EBU R128)",
        "measured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    with open(os.path.join(output_dir, "loudness.json"), "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    return data


def handle_plan(data):
    request = build_request(data)
    sampling_kwargs = build_sampling(data)
    output_dir = f"/tmp/{request['id']}"

    plan = plan_with_bpm(request, sampling_kwargs, normalize_bpm(data.get("bpm")))
    plan.save(output_dir)

    with open(os.path.join(output_dir, "request.json"), "w", encoding="utf-8") as fh:
        json.dump(request, fh, indent=2)

    upload = upload_artifacts(output_dir, request["id"], PLAN_NAMES)

    return {
        "status": "planned",
        "score_abc": plan.abc,
        "timing": {"abc": plan.timing},
        "seed": request["seed"],
        "truncated": {"abc": plan.truncated, "semantic": False},
        "output_dir": output_dir,
        "audio_path": None,
        **upload,
    }


def handle_generate(data):
    request = build_request(data)
    sampling_kwargs = build_sampling(data)
    output_dir = f"/tmp/{request['id']}"

    bpm = normalize_bpm(data.get("bpm"))
    if bpm and not request.get("abc"):
        # Plan first so the requested tempo can be enforced, then render the
        # adjusted score as the external composition.
        plan = plan_with_bpm(request, sampling_kwargs, bpm)
        request = {**request, "abc": plan.abc}

    song = pipe(**request, **sampling_kwargs)
    song.save_artifacts(output_dir)

    extras = {}

    # Decoder choice is real: decoding the same latents with a second VAE is
    # cheap relative to synthesis. The chosen decoder is the primary
    # audio.flac; the other one is kept alongside for A/B.
    decoder = str(data.get("decoder") or "standard").strip().lower()
    dual = bool(data.get("dual_decode"))
    if decoder == "legacy" or dual:
        legacy_vae = str(data.get("legacy_vae") or LEGACY_VAE_ID)
        if decoder == "legacy":
            # Standard decode (already written by save_artifacts) becomes the
            # extra; the legacy decode becomes the primary audio.flac.
            os.replace(
                os.path.join(output_dir, "audio.flac"),
                os.path.join(output_dir, "audio-standard.flac"),
            )
            audio_legacy = pipe.decode(song.latents, vae=legacy_vae)
            sf.write(
                os.path.join(output_dir, "audio.flac"),
                audio_legacy,
                song.sample_rate,
                subtype="PCM_24",
            )
            extras["decode"] = {"primary": "legacy", "legacy_vae": legacy_vae}
        else:
            # Standard stays primary; the legacy decode is the extra.
            audio_legacy = pipe.decode(song.latents, vae=legacy_vae)
            sf.write(
                os.path.join(output_dir, "audio-legacy.flac"),
                audio_legacy,
                song.sample_rate,
                subtype="PCM_24",
            )
            extras["decode"] = {"primary": "standard", "legacy_vae": legacy_vae}

    audio_formats = data.get("audio_formats")
    if isinstance(audio_formats, list) and audio_formats:
        extras["formats"] = convert_formats(
            output_dir, [str(fmt).lower() for fmt in audio_formats]
        )

    if data.get("analyze_loudness"):
        extras["loudness"] = measure_loudness(output_dir)

    upload = upload_artifacts(
        output_dir, request["id"], GENERATE_NAMES + EXTRA_NAMES
    )

    return {
        "status": "completed",
        "audio_path": f"{output_dir}/audio.flac",
        "output_dir": output_dir,
        "seed": request["seed"],
        "truncated": song.truncated,
        "extras": extras,
        **upload,
    }


def handler(job):
    data = job.get("input", {})

    if not data.get("style"):
        return {"error": "Missing 'style'."}

    if not data.get("lyrics"):
        return {"error": "Missing 'lyrics'."}

    action = str(data.get("action") or "generate").strip().lower()
    if action == "plan":
        return handle_plan(data)
    return handle_generate(data)


if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})
