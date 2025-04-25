import replicate
import os

os.environ["REPLICATE_API_TOKEN"] = "TU_TOKEN_AQUÍ"

# Puedes reemplazar esto por cualquier prompt
prompt = "a futuristic cityscape, highly detailed, at sunset"

# Usa el modelo + versión correctos
output = replicate.run(
    "stability-ai/stable-diffusion-3@db21e45a7190103d5c4f6d4f6c5c6ef18f3c8f34c74818d62d78b1dfb7b80b0c",
    input={"prompt": prompt}
)

print("✅ Imagen generada:", output)
