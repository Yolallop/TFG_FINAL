# test_rag_full.py
import app

def main():
    print("=== Probando google_search ===")
    resultados = app.google_search("inversiones")
    print(f"Obtuve {len(resultados)} resultados")
    # Muestra título y snippet del primero:
    primero = resultados[0]
    print("Primer resultado:")
    print("  title  =", primero.get("title"))
    print("  snippet=", primero.get("snippet"))
    print("  link   =", primero.get("link"))

    print("\n=== Probando rag_generate_script ===")
    raw = app.rag_generate_script("inversiones")
    print("\n--- GUION RAW (primeros 500 chars) ---")
    print(raw[:500].replace("\n", " "), "…")

    limpio = app.limpiar_guion(raw)
    print("\n--- GUION LIMPIO (primeros 500 chars) ---")
    print(limpio[:500].replace("\n", " "), "…")

if __name__ == "__main__":
    main()
