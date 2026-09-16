import os
import uuid
import runpod
import requests

from yue2 import YuE2Pipeline


MODEL_ID = os.getenv("YUE_MODEL", "m-a-p/YuE2-3B")
VAE_ID = os.getenv("YUE_VAE", "m-a-p/YuE2-Vae")
UPLOAD_URL = os.getenv("ARTIFACT_UPLOAD_URL", "").strip()
UPLOAD_TOKEN = os.getenv("ARTIFACT_UPLOAD_TOKEN", "").strip()
UPLOAD_NAMES = (
    "audio.flac",
    "score.abc",
    "plan.json",
    "result.json",
    "config.json",
    "request.json",
)

print("Loading YuE2...")

pipe = YuE2Pipeline.from_pretrained(
    MODEL_ID,
    vae=VAE_ID,
    device="cuda",
)

print("YuE2 loaded.")


def upload_artifacts(output_dir, generation_id):
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
        for name in UPLOAD_NAMES:
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


def handler(job):
    data = job.get("input", {})

    style = data.get("style")
    lyrics = data.get("lyrics")

    if not style:
        return {"error": "Missing 'style'."}

    if not lyrics:
        return {"error": "Missing 'lyrics'."}

    request = {
        "id": data.get("id", str(uuid.uuid4())),
        "style": style,
        "lyrics": lyrics,
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

    # Optional sampling overrides (abc_sampling / semantic_sampling). The
    # Sampling dataclass validates the ranges; semantic max_tokens is what
    # caps the song length (25 codec tokens ≈ 1 second).
    sampling_kwargs = {}
    abc_sampling = data.get("abc_sampling")
    if isinstance(abc_sampling, dict) and abc_sampling:
        sampling_kwargs["abc_sampling"] = abc_sampling
    semantic_sampling = data.get("semantic_sampling")
    if isinstance(semantic_sampling, dict) and semantic_sampling:
        sampling_kwargs["semantic_sampling"] = semantic_sampling

    output_dir = f"/tmp/{request['id']}"

    song = pipe(**request, **sampling_kwargs)

    song.save_artifacts(output_dir)

    upload = upload_artifacts(output_dir, request["id"])

    return {
        "status": "completed",
        "audio_path": f"{output_dir}/audio.flac",
        "output_dir": output_dir,
        "seed": request["seed"],
        "truncated": song.truncated,
        **upload,
    }


if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})
