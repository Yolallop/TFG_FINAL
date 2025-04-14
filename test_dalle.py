import openai
import base64
import os
from config import OPENAI_API_KEY

openai.api_key = OPENAI_API_KEY

def generar_imagen(prompt: str, nombre_archivo: str):
    response = openai.images.generate(
        model="dall-e-3",
        prompt=prompt,
        size="1024x1024",
        quality="standard",
        n=1,
        response_format="b64_json"
    )

    image_data = response.data[0].b64_json
    image_bytes = base64.b64decode(image_data)

    os.makedirs("static/imagenes_generadas", exist_ok=True)
    ruta_salida = f"static/imagenes_generadas/{nombre_archivo}.png"
    with open(ruta_salida, "wb") as f:
        f.write(image_bytes)

    print(f"✅ Imagen generada en: {ruta_salida}")
    return ruta_salida

# Prueba
generar_imagen("Ilustración de una profesora explicando inteligencia artificial", "prueba_ai")
