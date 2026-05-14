"""
TP1 - Exercice 1 : Structures de données Redis
Use Case : ShopFast - Gestion des produits, paniers et navigation
"""
import redis
import json

r = redis.Redis(host='localhost', port=6379, decode_responses=True)


def store_product(r, product_id, product_data: dict):
    """
    Stocker un produit comme Hash Redis
    Clé : "product:{product_id}"
    Champs : name, price, category, stock

    On utilise HSET avec mapping= pour stocker
    tous les champs du dict en une seule commande.

    >>> store_product(r, 1, {"name": "Samsung A54", "price": 65000,
    ...                      "category": "phones", "stock": 15})
    """
    r.hset(f"product:{product_id}", mapping=product_data)


def get_product(r, product_id):
    """
    Récupérer un produit par son ID via HGETALL.
    Retourne None si la clé n'existe pas (dict vide → None).
    """
    data = r.hgetall(f"product:{product_id}")
    # HGETALL renvoie {} si la clé est absente → on normalise à None
    return data if data else None


def add_to_cart(r, user_id, product_id, quantity: int = 1):
    """
    Ajouter / incrémenter un produit dans le panier.
    Clé  : "cart:{user_id}"   (Hash)
    Champ : str(product_id)  → quantité cumulée

    HINCRBY crée le champ s'il n'existe pas encore,
    puis l'incrémente de `quantity`.
    """
    r.hincrby(f"cart:{user_id}", str(product_id), quantity)


def get_cart(r, user_id):
    """
    Récupérer tout le contenu du panier.
    Retourne un dict {product_id: quantity} (valeurs en str côté Redis).
    """
    return r.hgetall(f"cart:{user_id}")


def record_view(r, user_id, product_id, max_history: int = 10):
    """
    Enregistrer un produit consulté par l'utilisateur.
    Clé : "history:{user_id}"  (List)

    Stratégie :
      - LPUSH  → insère en tête (le plus récent en position 0)
      - LTRIM  → garde seulement les max_history premiers éléments
    Ainsi la liste ne dépasse jamais max_history entrées.
    """
    key = f"history:{user_id}"
    r.lpush(key, str(product_id))
    # LTRIM(key, 0, max_history-1) supprime tout ce qui dépasse
    r.ltrim(key, 0, max_history - 1)


def get_history(r, user_id):
    """
    Récupérer l'historique de navigation (du plus récent au plus ancien).
    LRANGE 0 -1 → tous les éléments de la liste.
    """
    return r.lrange(f"history:{user_id}", 0, -1)


def add_product_to_category(r, category: str, product_id):
    """
    Associer un produit à une catégorie.
    Clé : "category:{category}"  (Set)

    SADD garantit l'unicité : un même produit
    ne sera jamais ajouté deux fois dans le même Set.
    """
    r.sadd(f"category:{category}", str(product_id))


def get_products_in_categories(r, *categories):
    """
    Récupérer les produits présents dans TOUTES les catégories données.
    Ex : produits "electronics" ET "promo" en même temps.

    SINTER calcule l'intersection de N Sets en une seule commande Redis.
    """
    keys = [f"category:{cat}" for cat in categories]
    return r.sinter(*keys)


# ─────────────────────────── test manuel ───────────────────────────
if __name__ == "__main__":
    r.flushdb()

    # ── Produits ──────────────────────────────────────────────────
    store_product(r, 1, {
        "name": "Samsung A54", "price": "65000",
        "category": "phones", "stock": "15"
    })
    store_product(r, 2, {
        "name": "Laptop HP", "price": "120000",
        "category": "laptops", "stock": "8"
    })
    store_product(r, 3, {
        "name": "Casque JBL", "price": "12000",
        "category": "audio", "stock": "50"
    })

    print("Produit #1 :", get_product(r, 1))
    print("Produit #99 (inexistant) :", get_product(r, 99))

    # ── Panier ────────────────────────────────────────────────────
    add_to_cart(r, "user:42", 1, 2)   # 2x Samsung A54
    add_to_cart(r, "user:42", 2, 1)   # 1x Laptop HP
    add_to_cart(r, "user:42", 1, 1)   # +1 Samsung A54 → total 3
    print("\nPanier user:42 :", get_cart(r, "user:42"))

    # ── Historique ────────────────────────────────────────────────
    for pid in [1, 2, 1, 3, 2, 4, 5, 6, 7, 8, 9, 10, 11]:
        record_view(r, "user:42", pid)
    hist = get_history(r, "user:42")
    print(f"\nHistorique (max 10 éléments) : {hist}")
    print(f"Longueur : {len(hist)} (attendu ≤ 10)")

    # ── Catégories ────────────────────────────────────────────────
    add_product_to_category(r, "electronics", 1)
    add_product_to_category(r, "electronics", 2)
    add_product_to_category(r, "promo",       1)
    add_product_to_category(r, "promo",       3)

    print("\nProduits electronics :", r.smembers("category:electronics"))
    print("Produits promo       :", r.smembers("category:promo"))
    print("Intersection (electronics ∩ promo) :",
          get_products_in_categories(r, "electronics", "promo"))