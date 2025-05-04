# test_factcheck.py
from app import fact_check_claim
from config import GOOGLE_API_KEY

print("Google API Key:", GOOGLE_API_KEY)
claims = fact_check_claim("La tasa de abandono de cursos es menor al 10%")
print("Claims:", claims)
import logging

logging.basicConfig(level=logging.INFO)

print("Google API Key:", GOOGLE_API_KEY)
logging.info("Google API Key: %s", GOOGLE_API_KEY)

claims = fact_check_claim("La tasa de abandono de cursos es menor al 10%")
logging.info("Claims: %s", claims)