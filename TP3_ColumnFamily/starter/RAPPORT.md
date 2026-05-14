
# RAPPORT TP3 — Cassandra : SmartGrid DZ

**Étudiant :** MESSAOUDI Abdelkrim  
**Module :** Bases de Données Avancées

---

## 1. Justification des Partition Keys

### Table `mesures_par_capteur` → `(capteur_id, date_jour)`

| Option envisagée       | Problème                                                                |
|------------------------|-------------------------------------------------------------------------|
| `(capteur_id)` seul    | 90 jours × 1 440 mesures = **129 600 lignes/partition** → trop grand      |
| `(wilaya, date_jour)`  | Alger = 4 000 capteurs × 1 440 = **5,76 M lignes/partition** → hot partition |
| `(capteur_id, date_jour)`  | **1 440 lignes/partition** — taille stable et prévisible                |

Le bucket quotidien `date_jour` est la clé du design.
Il garantit qu'une partition ne grandit jamais au-delà de
**1 440 lignes** (une mesure par minute sur 24h).
Après 90 jours, le TTL supprime les partitions entières,
libérant le disque de façon prévisible.

---

### Table `alertes_par_wilaya` → `(wilaya, date_jour)`

| Option envisagée        | Problème                                                  |
|-------------------------|-----------------------------------------------------------|
| `(wilaya)` seul         | Des années d'alertes dans une seule partition → illimité    |
| `(capteur_id, date_jour)` | Impossible de lire toutes les alertes d'une wilaya        |
| `(wilaya, date_jour)`   | Max ~500 alertes/jour/wilaya — requête naturelle          |

La requête métier est *"alertes d'Alger aujourd'hui"*.
La partition key doit donc contenir `wilaya` ET `date_jour`
pour que cette requête soit exécutée sans scan global.

---

### Table `agregats_horaires` → `(wilaya, date_jour)`

24 lignes par partition (une par heure).
Partition minuscule, lecture ultra-rapide pour le dashboard.
Le TTL de 5 ans conserve l'historique pour les analyses long terme.

---

## 2. Pourquoi `ALLOW FILTERING` est dangereux en production

### Ce que fait Cassandra sans `ALLOW FILTERING`

```
Requête → hash(partition_key) → nœud responsable → lecture locale
Latence : < 1 ms
```

### Ce que fait Cassandra avec `ALLOW FILTERING`

```
Requête → broadcast sur TOUS les nœuds
         → chaque nœud scanne TOUTES ses partitions
         → filtre les lignes qui correspondent
         → agrège les résultats côté coordinateur
Latence : secondes à minutes
```

### Impact concret sur SmartGrid DZ

```
10 000 capteurs × 90 jours = 900 000 partitions

ALLOW FILTERING sur mesures_par_capteur :
  → 900 000 partitions lues
  → ~129 millions de lignes scannées
  → Charge CPU : 100 % sur tous les nœuds
  → Latence : timeout (30 s par défaut)
  → Risque : cascade de timeouts → indisponibilité du cluster
```

### Règle à appliquer

> Pour chaque requête fréquente → créer une table dédiée
> avec la partition key adaptée à cette requête.

`ALLOW FILTERING` est acceptable **uniquement** si la
partition est déjà ciblée et que le filtre supplémentaire
s'applique sur un petit nombre de lignes connues.

---

## 3. Comparaison TWCS vs STCS vs LCS

| Critère                  | STCS                                  | TWCS                                 | LCS                                 |
|--------------------------|---------------------------------------|--------------------------------------|-------------------------------------|
| **Principe**             | Regroupe SSTables de taille similaire | Regroupe par fenêtre temporelle      | Regroupe par niveau de taille       |
| **Write throughput**     | Excellent                          |  Excellent                         |  Moyen (write amplification)      |
| **Read latency**         |  Variable                           |  Variable                          |  Stable et faible                 |
| **Libération TTL**       |  Lente                              |  Rapide (par fenêtre)              |  Lente                            |
| **Espace disque**        |  Imprévisible                       |  Prévisible                        |  Compact                          |
| **Complexité CPU**       | Faible                                | Faible                               | Élevée                              |

### Quand utiliser chacun ?

**TWCS — séries temporelles (notre choix pour `mesures_par_capteur`)**
- Données horodatées avec TTL
- Ingestion massive en continu (IoT, logs, métriques)
- Les données passées ne sont jamais modifiées
- La fenêtre de compaction doit correspondre au bucket de la partition key

```sql
-- Fenêtre = 1 jour car date_jour est notre bucket
'compaction_window_unit' : 'DAYS',
'compaction_window_size' : 1
```

**STCS — workload write-heavy sans TTL**
- Données sans date d'expiration
- Peu de lectures, beaucoup d'écritures
- Cas d'usage : journaux d'événements permanents

**LCS — workload read-heavy avec peu d'écritures**
- Données lues très fréquemment
- Peu de nouvelles écritures (données stables)
- Cas d'usage : table `agregats_horaires` (dashboard lu en permanence, écrite une fois par heure seulement)

---

### Résumé pour SmartGrid DZ

| Table                  | Stratégie | Justification                              |
|------------------------|-----------|--------------------------------------------|
| `mesures_par_capteur`  | **TWCS**  | IoT horodaté, TTL 90 j, ingestion massive  |
| `alertes_par_wilaya`   | **TWCS**  | IoT horodaté, TTL 1 an, moins fréquent     |
| `agregats_horaires`    | **LCS**   | Peu d'écritures, lecture dashboard continue|
```