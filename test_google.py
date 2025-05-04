# test_rag_full.py
import app, pprint

def main():
    print("=== Test de google_search ===")
    res = app.google_search("inversiones")
    print(f"Obtuve {len(res)} resultados")
    pprint.pprint(res[0])

    print("\n=== Test de rag_generate_script ===")
    raw = app.rag_generate_script("inversiones")
    print("\n--- GUION RAW (primeros 500 chars) ---")
    print(raw[:500], "…")

    limpio = app.limpiar_guion(raw)
    print("\n--- GUION LIMPIO (primeros 500 chars) ---")
    print(limpio[:500], "…")

if __name__ == "__main__":
    main()
