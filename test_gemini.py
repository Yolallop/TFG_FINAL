import google.generativeai as genai
from config import GEMINI_API_KEY

genai.configure(api_key=GEMINI_API_KEY)

model = genai.GenerativeModel(model_name="models/gemini-1.5-pro")

response = model.generate_content("Explícame cómo funciona la inteligencia artificial.")
print(response.text)
