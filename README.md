import replicate

client = replicate.Client(api_token="AQUÍ_TU_TOKEN_REAL")

result = client.run(
    "stability-ai/stable-diffusion",
    input={"prompt": "A fantasy castle at sunset"}
)

print(result)
