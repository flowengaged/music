import os
import uuid
import runpod

from yue2 import YuE2Pipeline


MODEL_ID = os.getenv("YUE_MODEL", "m-a-p/YuE2-3B")
VAE_ID = os.getenv("YUE_VAE", "m-a-p/YuE2-Vae")

print("Loading YuE2...")

pipe = YuE2Pipeline.from_pretrained(
    MODEL_ID,
    vae=VAE_ID,
    device="cuda",
)

print("YuE2 loaded.")


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

    output_dir = f"/tmp/{request['id']}"

    song = pipe(**request)

    song.save_artifacts(output_dir)

    return {
        "status": "completed",
        "audio_path": f"{output_dir}/audio.flac",
        "output_dir": output_dir,
        "seed": request["seed"],
        "truncated": song.truncated,
    }


if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})
