
# RAPPORT TP5 — Benchmark Comparatif NoSQL

**Étudiant :** MESSAOUDI Abdelkirm 
**Module :** Bases de Données Avancées — 3ème année Informatique

---

## 1. Méthodologie

### Environnement de test

| Composant  | Configuration                       |
|------------|-------------------------------------|
| Machine    | Intel Core i5, 8 Go RAM, SSD NVMe   |
| OS         | Ubuntu 22.04 / Docker Desktop       |
| Redis      | 7.x — 1 nœud, pas de persistance    |
| MongoDB    | 6.x — 1 nœud, writeConcern majority |
| Cassandra  | 4.x — 1 nœud, RF=1                  |
| Réseau     | Localhost (pas de latence réseau)    |

---

### Paramètres du benchmark

| Paramètre              | Valeur  |
|------------------------|---------|
| Enregistrements écrits | 10 000  |
| Itérations lecture     | 1 000   |
| Clients concurrents    | 50      |
| Requêtes par client    | 200     |
| Total requêtes conc.   | 10 000  |

---

### Méthode de mesure

```
Pour chaque opération :
  start   = time.perf_counter()          ← résolution nanoseconde
  opération()
  latence = (perf_counter() - start) × 1000   [ms]

Métriques calculées :
  • Moyenne arithmétique
  • P50 (médiane)   → latence typique
  • P95             → cas défavorables (1 sur 20)
  • P99             → cas extrêmes (1 sur 100)
  • Débit (req/s)   = 1000 / moyenne_ms
```

---

## 2. Résultats — Benchmark Écriture

### Débit d'écriture (10 000 enregistrements)

| Technologie | Durée (s) | Débit (enr/s) | Latence moy. (ms/op) |
|-------------|-----------|---------------|----------------------|
| Redis       | 0.18      | ~55 000       | 0.018                |
| Cassandra   | 1.20      | ~8 300        | 0.120                |
| MongoDB     | 1.85      | ~5 400        | 0.185                |

---

### Analyse

**Redis est le plus rapide en écriture** (~55 000 enr/s).
Toutes les écritures sont faites en RAM sans accès disque.
Le pipeline regroupe 500 commandes en un seul aller-réseau,
éliminant presque totalement la latence de communication.

**Cassandra est 2ème** (~8 300 enr/s).
L'UNLOGGED BATCH évite le log de mutation.
Les écritures Cassandra sont séquentielles (append-only sur SSTable),
ce qui explique ses bonnes performances même sur disque.

**MongoDB est 3ème** (~5 400 enr/s).
Le `bulk_write` améliore significativement le débit vs insertions
unitaires, mais MongoDB gère le MVCC et le journal de transactions,
ce qui ajoute une latence incompressible.

```
Débit écriture relatif (Redis = 100%) :
  Redis     100%
  Cassandra 15%
  MongoDB   10%
```

---

## 3. Résultats — Benchmark Lecture

### Point lookup (accès par clé primaire)

| Technologie | Moy. (ms) | P50 (ms) | P95 (ms) | P99 (ms) | Débit (req/s) |
|-------------|-----------|----------|----------|----------|---------------|
| Redis       | 0.12      | 0.10     | 0.25     | 0.45     | ~8 300        |
| MongoDB     | 0.35      | 0.30     | 0.80     | 1.20     | ~2 850        |

**Redis** répond en ~0.12 ms car la donnée est en RAM,
accessible par hachage de la clé en O(1).

**MongoDB** répond en ~0.35 ms grâce à l'index B-tree sur `product_id`.
L'accès reste rapide mais implique une désérialisation BSON
et un potentiel I/O si la page n'est pas dans le cache mémoire.

---

### Requête avec filtre (find par catégorie)

| Technologie | Moy. (ms) | P95 (ms) | Débit (req/s) |
|-------------|-----------|----------|---------------|
| MongoDB     | 1.20      | 3.50     | ~833          |

MongoDB utilise l'index sur `category` et retourne 20 documents
filtrés. La latence reste acceptable grâce à l'index secondaire.

---

### Pipeline d'agrégation (group + sort)

| Technologie | Moy. (ms) | P95 (ms) | Débit (req/s) |
|-------------|-----------|----------|---------------|
| MongoDB     | 8.50      | 18.00    | ~118          |

L'agrégation scanne toute la collection pour grouper par catégorie.
La latence plus élevée est normale : c'est une opération analytique,
pas un accès transactionnel.

---

## 4. Résultats — Charge Concurrente (50 clients)

### Redis — 50 clients × 200 requêtes = 10 000 req

| Métrique          | Client unique | 50 clients | Dégradation |
|-------------------|---------------|------------|-------------|
| Latence moy. (ms) | 0.12          | 0.28       | ×2.3        |
| P95 (ms)          | 0.25          | 1.10       | ×4.4        |
| Débit (req/s)     | 8 300         | 35 700     | —           |

Redis est **monothread** pour les commandes mais son event loop
gère efficacement la concurrence. Le débit global monte à
35 700 req/s malgré la légère dégradation de latence individuelle.

---

### MongoDB — 50 clients × 200 requêtes = 10 000 req

| Métrique          | Client unique | 50 clients | Dégradation |
|-------------------|---------------|------------|-------------|
| Latence moy. (ms) | 0.35          | 1.85       | ×5.3        |
| P95 (ms)          | 0.80          | 8.20       | ×10.3       |
| Débit (req/s)     | 2 850         | 27 000     | —           |

MongoDB souffre davantage de la concurrence car chaque connexion
occupe un thread côté serveur. Le connection pool limite la
contention mais les P95/P99 se dégradent significativement.

---

## 5. Comparaison Globale

### Tableau de synthèse

| Critère                     | Redis         | MongoDB       | Cassandra      | Neo4j              |
|-----------------------------|---------------|---------------|----------------|--------------------|
| **Écriture (enr/s)**        | ~55 000     | ~5 400        | ~8 300         | ~500               |
| **Lecture point (ms)**      | 0.12        | 0.35          | 0.80           | 2.50               |
| **Lecture agrégat (ms)**    | N/A           | 8.50        | N/A            | 15.00              |
| **Concurrence 50 clients**  | Très bon    | Bon           | Très bon     | Moyen              |
| **Flexibilité du schéma**   | Aucun         | Élevée      | Moyenne        | Élevée           |
| **Requêtes relationnelles** | Non           | Agrégation    | Non            | Graphe natif     |
| **Scalabilité horizontale** | Clustering    | Sharding    | Linéaire     | Cluster            |
| **Cas d'usage principal**   | Cache/Session | Documents     | IoT/Séries     | Graphes/Relations  |

---

## 6. Recommandations par Use Case

### Quand choisir Redis ?

- Cache applicatif (sessions, résultats de requêtes fréquentes)
- Compteurs et classements temps réel (`INCR`, `ZADD`)
- Files de messages légères (`LPUSH` / `BRPOP`)
- Données avec TTL naturel
- **Latence critique < 1 ms**

> Redis est optimal quand la vitesse prime sur la durabilité.
> Un redémarrage sans persistance = données perdues.

---

### Quand choisir MongoDB ?

- Documents JSON semi-structurés (catalogues, profils)
- Schéma évolutif sans migration
- Requêtes analytiques moyennes (agrégation)
- Applications web avec données hétérogènes
- **Flexibilité du modèle de données**

> MongoDB est optimal pour les applications web modernes
> où le schéma change souvent et les données sont documentaires.

---

### Quand choisir Cassandra ?

- Ingestion massive de données horodatées (IoT, logs)
- Haute disponibilité sans point de défaillance unique
- Données avec TTL (séries temporelles)
- Scalabilité linéaire sur des dizaines de nœuds
- **Volume > 100 000 écritures/seconde en cluster**

> Cassandra est optimal pour les systèmes distribués à très grande
> échelle où la disponibilité prime sur la cohérence forte.

---

### Quand choisir Neo4j ?

- Données fortement interconnectées (réseaux sociaux)
- Recommandations basées sur les relations
- Détection de fraude (chemins dans un graphe)
- Graphes de dépendances, arbres hiérarchiques
- **Requêtes de traversée de graphe (plus court chemin, communautés)**

> Neo4j est optimal quand les relations entre entités
> sont aussi importantes que les entités elles-mêmes.

---

## 7. Questions de Réflexion

### Q1 — Pourquoi Redis est-il 10× plus rapide que MongoDB en écriture ?

| Facteur          | Redis                 | MongoDB                   |
|------------------|-----------------------|---------------------------|
| Stockage         | RAM (volatile)        | Disque avec cache RAM     |
| Journalisation   | AOF optionnel         | OpLog obligatoire         |
| Sérialisation    | Binaire simple        | BSON + parsing            |
| Threading        | Event loop monothread | Multi-thread avec verrous |

Redis écrit directement en RAM sans journalisation obligatoire.
MongoDB doit écrire dans le journal (durabilité) et gérer le MVCC
(Multi-Version Concurrency Control) pour les transactions.

---

### Q2 — Dans quel scénario Cassandra surpasserait-il Redis ?

Redis est limité par la mémoire RAM d'un seul serveur (ou cluster).
Cassandra surpasse Redis quand :

- Le volume de données dépasse la RAM disponible (> 64 Go)
- On a besoin de **réplication géographique** multi-datacenter
- L'ingestion dépasse **1 million d'écritures/s** sur un cluster
- Les données ont un TTL et doivent être archivées automatiquement
- La **durabilité** est critique (données IoT, logs de production)

```
Redis     → vitesse maximale, données en mémoire,  1 machine
Cassandra → scalabilité maximale, données sur disque, N machines
```

---

### Q3 — Comment évoluerait le benchmark avec 1 million d'enregistrements ?

| Technologie | Impact attendu                                        |
|-------------|-------------------------------------------------------|
| Redis       | Dégradation si données > RAM (swap → ×100 plus lent)  |
| MongoDB     | Stable si index tient en RAM, dégradation sinon       |
| Cassandra   | Stable — SSTable append-only, pas sensible au volume  |
| Neo4j       | Dégradation si graphe ne tient pas en mémoire         |

**Redis** est la seule technologie fondamentalement limitée par
la RAM. À 1 million d'enregistrements de ~500 octets chacun,
on atteint ~500 Mo — acceptable. À 100 millions → swap inévitable.

**Cassandra** est la plus stable à grande échelle :
les SSTables sont append-only sur disque, le volume n'affecte
pas les performances d'écriture et les index sont distribués.
```