"""
TP1 - Exercice 3 : Pattern Cache-Aside avec TTL
Use Case : Cache des pages produits ShopFast
"""
import redis
import json
import time
from typing import Optional

r = redis.Redis(host='localhost', port=6379, decode_responses=True)


# ───────────────────────── simulation DB ──────────────────────────
def slow_db_get_product(product_id: int) -> Optional[dict]:
    """
    Simule une requête PostgreSQL lente (~2 secondes).
    En production ce serait un vrai appel psycopg2 / SQLAlchemy.
    """
    time.sleep(2)
    products = {
        1: {"id": 1, "name": "Samsung Galaxy A54",  "price": 65000,  "stock": 15},
        2: {"id": 2, "name": "Laptop HP 15-inch",   "price": 120000, "stock": 8},
        3: {"id": 3, "name": "Casque JBL Bluetooth","price": 12000,  "stock": 50},
        4: {"id": 4, "name": "Clavier Mécanique",   "price": 8000,   "stock": 30},
    }
    return products.get(product_id)


# ──────────────────────── Cache-Aside core ────────────────────────
def get_product_cached(r, product_id: int, ttl: int = 600) -> Optional[dict]:
    """
    Pattern Cache-Aside en 3 étapes :

      1. GET  dans Redis  (lecture rapide)
           → HIT  : désérialiser et retourner immédiatement
           → MISS : continuer vers l'étape 2

      2. Requête vers la base de données (lente)

      3. SETEX dans Redis avec TTL
           Stocker le résultat pour les prochaines requêtes,
           puis retourner la donnée.

    TTL par défaut : 600 s (10 min) — bon compromis
    entre fraîcheur des données et réduction de charge DB.
    """
    start     = time.time()
    cache_key = f"product_cache:{product_id}"

    # ── Étape 1 : lecture Redis ────────────────────────────────────
    cached_value = r.get(cache_key)

    if cached_value is not None:
        # ── CACHE HIT ─────────────────────────────────────────────
        elapsed_ms = (time.time() - start) * 1000
        print(f"  ✅ CACHE HIT  — {elapsed_ms:.1f} ms  (produit #{product_id})")
        return json.loads(cached_value)

    # ── Étape 2 : appel DB (MISS) ─────────────────────────────────
    product = slow_db_get_product(product_id)
    elapsed_ms = (time.time() - start) * 1000

    # ── Étape 3 : mise en cache si le produit existe ───────────────
    if product is not None:
        # SETEX = SET + EX (expire dans `ttl` secondes)
        r.setex(cache_key, ttl, json.dumps(product))

    print(f"  ❌ CACHE MISS — {elapsed_ms:.1f} ms  (produit #{product_id})")
    return product


def invalidate_product_cache(r, product_id: int):
    """
    Invalider (supprimer) le cache d'un produit.
    À appeler après toute mise à jour en base de données
    pour éviter de servir une donnée obsolète (stale data).
    """
    deleted = r.delete(f"product_cache:{product_id}")
    if deleted:
        print(f"  🗑️  Cache invalidé pour le produit #{product_id}")
    else:
        print(f"  ⚠️  Aucun cache trouvé pour le produit #{product_id}")


def benchmark_cache(r, product_id: int, iterations: int = 20):
    """
    Mesure les performances du cache sur `iterations` appels.

    Méthode :
      - On supprime d'abord la clé → garantit 1 seul MISS au départ
      - Les appels suivants seront tous des HITs
      - On collecte les temps et on affiche les statistiques
    """
    hit_times:  list[float] = []
    miss_times: list[float] = []

    # Repartir d'un état propre
    r.delete(f"product_cache:{product_id}")

    print(f"\n  Lancement du benchmark : {iterations} itérations "
          f"sur le produit #{product_id}")
    print("  " + "─" * 45)

    for i in range(iterations):
        start      = time.time()
        cache_key  = f"product_cache:{product_id}"
        cached_val = r.get(cache_key)
        is_hit     = cached_val is not None

        if not is_hit:
            # MISS → requête DB + mise en cache
            product = slow_db_get_product(product_id)
            if product is not None:
                r.setex(cache_key, 600, json.dumps(product))

        elapsed_ms = (time.time() - start) * 1000

        if is_hit:
            hit_times.append(elapsed_ms)
        else:
            miss_times.append(elapsed_ms)

    # ── Rapport ───────────────────────────────────────────────────
    total     = len(hit_times) + len(miss_times)
    hit_rate  = len(hit_times) / total * 100

    print(f"\n  {'─'*45}")
    print(f"  📊 Résultats benchmark ({iterations} itérations)")
    print(f"  {'─'*45}")

    if miss_times:
        avg_miss = sum(miss_times) / len(miss_times)
        print(f"  ❌ MISS — n={len(miss_times):>3}  |  moy = {avg_miss:>8.1f} ms")

    if hit_times:
        avg_hit = sum(hit_times) / len(hit_times)
        print(f"  ✅ HIT  — n={len(hit_times):>3}  |  moy = {avg_hit:>8.1f} ms")

    if miss_times and hit_times:
        speedup = avg_miss / avg_hit
        print(f"  ⚡ Accélération  : ×{speedup:.0f} plus rapide avec le cache")

    print(f"  🎯 Hit rate      : {hit_rate:.0f}%")
    print(f"  {'─'*45}")


# ─────────────────────────── test manuel ──────────────────────────
if __name__ == "__main__":
    r.flushdb()

    print("=" * 50)
    print("  TEST PATTERN CACHE-ASIDE")
    print("=" * 50)

    print("\n① Premier appel — MISS attendu (~2 s) :")
    p = get_product_cached(r, 1)
    print(f"     Résultat : {p}")

    print("\n② Deuxième appel — HIT attendu (<1 ms) :")
    p = get_product_cached(r, 1)
    print(f"     Résultat : {p}")

    print("\n③ Invalidation du cache :")
    invalidate_product_cache(r, 1)

    print("\n④ Appel après invalidation — MISS attendu :")
    get_product_cached(r, 1)

    print("\n⑤ Produit inexistant (id=99) :")
    get_product_cached(r, 99)

    print("\n\n" + "=" * 50)
    print("  BENCHMARK")
    print("=" * 50)
    benchmark_cache(r, 2, iterations=10)