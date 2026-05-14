"""
TP1 - Exercice 4 : Classement des meilleures ventes
Use Case : Top produits ShopFast en temps réel
"""
import redis
import random
from typing import Optional

r = redis.Redis(host='localhost', port=6379, decode_responses=True)

LEADERBOARD_KEY = "leaderboard:sales"


def record_sale(r, product_id, quantity: int = 1):
    """
    Enregistrer une vente dans le Sorted Set.

    ZINCRBY incrémente le score (= nb de ventes) du membre product_id.
    Si le membre n'existe pas encore, il est créé avec score = quantity.

    Clé    : LEADERBOARD_KEY
    Membre : str(product_id)
    Score  : nombre total de ventes (cumulé)
    """
    r.zincrby(LEADERBOARD_KEY, quantity, str(product_id))


def get_top_products(r, n: int = 10) -> list:
    """
    Retourner les N produits les plus vendus (score décroissant).

    ZREVRANGE + WITHSCORES renvoie une liste de tuples (member, score)
    triée du score le plus élevé au plus bas.

    Retourne :
      [{"product_id": "3", "sales": 245.0}, ...]
    """
    # ZREVRANGE : index 0 → meilleur, n-1 → Nième meilleur
    results = r.zrevrange(LEADERBOARD_KEY, 0, n - 1, withscores=True)

    return [
        {"product_id": member, "sales": score}
        for member, score in results
    ]


def get_product_rank(r, product_id) -> Optional[int]:
    """
    Retourner le rang 1-based d'un produit.
      Rang 1 = best seller (score le plus élevé)
      None   = produit absent du classement

    ZREVRANK renvoie un rang 0-based → on ajoute 1.
    """
    rank = r.zrevrank(LEADERBOARD_KEY, str(product_id))
    if rank is None:
        return None
    return rank + 1          # conversion 0-based → 1-based


def get_products_between_ranks(r, start_rank: int, end_rank: int) -> list:
    """
    Retourner les produits entre les rangs start_rank et end_rank (1-based inclus).
    Ex : rangs 3 à 7 → 5 produits (positions 3, 4, 5, 6, 7).

    ZREVRANGE utilise des index 0-based :
      start_rank=3, end_rank=7  →  index 2 à 6
    """
    start_idx = start_rank - 1
    end_idx   = end_rank   - 1

    results = r.zrevrange(LEADERBOARD_KEY, start_idx, end_idx, withscores=True)

    return [
        {"rank": start_rank + i, "product_id": member, "sales": score}
        for i, (member, score) in enumerate(results)
    ]


def simulate_sales_day(r, n_sales: int = 500):
    """
    Simuler une journée de ventes aléatoires sur les produits 1-20.
    Chaque transaction vend entre 1 et 5 unités.
    """
    products = list(range(1, 21))   # 20 produits
    for _ in range(n_sales):
        product_id = random.choice(products)
        qty        = random.randint(1, 5)
        record_sale(r, product_id, qty)


# ─────────────────────────── test manuel ──────────────────────────
if __name__ == "__main__":
    r.flushdb()

    print("=" * 50)
    print("  SIMULATION JOURNÉE DE VENTES (500 transactions)")
    print("=" * 50)
    simulate_sales_day(r, 500)

    # ── Top 5 ─────────────────────────────────────────────────────
    print("\n Top 5 produits les plus vendus :")
    print("  " + "─" * 35)
    for i, p in enumerate(get_top_products(r, 5), 1):
        bar = "█" * int(p["sales"] // 20)   # barre visuelle
        print(f"  {i}. Produit #{p['product_id']:>2} "
              f"— {int(p['sales']):>4} ventes  {bar}")

    # ── Rang individuel ───────────────────────────────────────────
    print("\n📍 Rangs individuels :")
    for pid in [1, 5, 10, 15, 20]:
        rank = get_product_rank(r, pid)
        print(f"  Produit #{pid:>2} → rang {rank}")

    # ── Plage de rangs ────────────────────────────────────────────
    print("\n Produits classés de la 3ème à la 7ème place :")
    print("  " + "─" * 40)
    for entry in get_products_between_ranks(r, 3, 7):
        print(f"  Rang {entry['rank']} | Produit #{entry['product_id']:>2} "
              f"| {int(entry['sales'])} ventes")