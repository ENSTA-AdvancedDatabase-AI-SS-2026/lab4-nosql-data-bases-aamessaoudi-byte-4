
# RAPPORT TP4 — Neo4j : Réseau Social UniConnect DZ

**Étudiant :** MESSAOUDI Abdelkrim 
**Module :** Bases de Données Avancées — 3ème année Informatique

---

## 1. Schéma du Graphe

### Nœuds et propriétés

| Label         | Propriétés clés                                     | Nb |
|---------------|-----------------------------------------------------|----|
| `:Etudiant`   | id, prenom, nom, universite, filiere, annee, ville  | 50 |
| `:Cours`      | code, intitule, credits, departement                | 10 |
| `:Competence` | nom, categorie                                      | 14 |
| `:Club`       | nom, universite, domaine                            | 5  |
| `:Entreprise` | nom, secteur, ville                                 | 8  |

---

### Relations

| Relation        | De → Vers               | Propriétés clés       |
|-----------------|-------------------------|-----------------------|
| `:CONNAIT`      | Etudiant → Etudiant     | depuis, contexte      |
| `:SUIT`         | Etudiant → Cours        | semestre, note        |
| `:MAITRISE`     | Etudiant → Competence   | niveau                |
| `:MEMBRE_DE`    | Etudiant → Club         | role                  |
| `:A_STAGE_CHEZ` | Etudiant → Entreprise   | annee, duree_mois     |
| `:REQUIERT`     | Cours → Competence      | —                     |

---

### Représentation ASCII du graphe

```
(Ahmed:Etudiant)──[:CONNAIT {depuis:2022}]──►(Fatima:Etudiant)
      │                                              │
      │[:SUIT {note:16.5}]                  [:SUIT {note:17.0}]
      ▼                                              ▼
(INFO401:Cours)────[:REQUIERT]────►(SQL:Competence)
      │
      └──[:REQUIERT]────►(NoSQL:Competence)

(Ahmed)──[:MEMBRE_DE {role:"Membre"}]──►(Club IA USTHB:Club)
(Ahmed)──[:MAITRISE  {niveau:"Avancé"}]──►(Python:Competence)
```

---

## 2. Résultats de l'Algorithme de Communautés (Louvain)

### Communautés détectées

L'algorithme de Louvain a détecté **5 communautés** principales,
qui correspondent naturellement aux universités d'appartenance.

| Communauté | Université dominante | Taille | Membres exemples                     |
|------------|----------------------|--------|--------------------------------------|
| C1         | USTHB                | 11     | Ahmed, Fatima, Mehdi, Lina, Amira    |
| C2         | UMBB                 | 10     | Karim, Youcef, Samia, Walid, Nazim   |
| C3         | USTO                 | 10     | Yasmina, Anis, Djamila, Nour, Lynda  |
| C4         | UMC                  | 10     | Rania, Tarek, Sabrina, Amine, Leila  |
| C5         | UBMA                 | 9      | Sara, Djamel, Nabila, Zineb, Sihem   |

---

### Analyse des communautés

**Observation 1 — Corrélation université / communauté**

Les communautés Louvain correspondent presque parfaitement
aux universités. Cela confirme que les étudiants se connectent
prioritairement avec leurs camarades de la même université
(cours partagés, même campus).

---

**Observation 2 — Étudiants "ponts"**

Quelques étudiants apparaissent entre deux communautés :
Ahmed (USTHB) est connecté à Karim (UMBB) et Yasmina (USTO)
via des hackathons et conférences.
Ces étudiants ont un score de **betweenness centrality** élevé :
ils jouent le rôle de pont entre des cercles sociaux distincts.

---

**Observation 3 — Modularité**

Une modularité proche de **0.7** (typique pour ce type de réseau)
indique des communautés bien séparées avec peu de liens
inter-communautés, ce qui est attendu pour un réseau universitaire
où les interactions restent majoritairement locales.

---

## 3. Comparaison SQL vs Cypher

### Requête : *"Amis d'amis d'Ahmed qui ne sont pas déjà ses amis"*

---

#### Version SQL

```sql
SELECT DISTINCT u3.prenom, u3.universite
FROM utilisateurs u1
JOIN amities a1 ON u1.id = a1.user1_id
JOIN utilisateurs u2 ON a1.user2_id = u2.id
JOIN amities a2 ON u2.id = a2.user1_id
JOIN utilisateurs u3 ON a2.user2_id = u3.id
WHERE u1.prenom = 'Ahmed'
  AND u3.id <> u1.id
  AND u3.id NOT IN (
    SELECT user2_id FROM amities WHERE user1_id = u1.id
    UNION
    SELECT user1_id FROM amities WHERE user2_id = u1.id
  );
```

**Complexité SQL :**

- 3 JOINs successifs sur la table `amities`
- 1 sous-requête de négation avec `NOT IN`
- Si la table `amities` contient N lignes → **O(N²)** dans le pire cas
- Difficile à étendre à 3 sauts (5 JOINs nécessaires)
- Extension à N sauts : **impossible** sans procédure stockée récursive

---

#### Version Cypher

```cypher
MATCH (ahmed:Etudiant {prenom: "Ahmed"})
      -[:CONNAIT]-(ami)-[:CONNAIT]-(suggestion:Etudiant)
WHERE NOT (ahmed)-[:CONNAIT]-(suggestion)
  AND suggestion <> ahmed
RETURN DISTINCT suggestion.prenom, suggestion.universite
```

**Complexité Cypher :**

- 1 seul pattern de traversée de graphe
- Aucun JOIN explicite nécessaire
- Extension à 3 sauts : `[:CONNAIT*3]` — un seul caractère à changer
- Extension à N sauts : `[:CONNAIT*..N]` — toujours une seule ligne

---

### Tableau comparatif

| Critère               | SQL                                | Cypher                           |
|-----------------------|------------------------------------|----------------------------------|
| Lisibilité            | Difficile (3+ JOINs imbriqués)     | Naturelle (chemin visuel)        |
| Extensibilité         | Réécriture complète à chaque saut  | `*N` suffit                      |
| Performance           | Dégradation exponentielle          | Index de graphe natif O(log N)   |
| Plus court chemin     | Impossible sans procédure stockée  | `shortestPath()` natif           |
| Détection de cycle    | Très complexe                      | `[:REL*]` natif                  |
| Communautés           | Impossible en SQL pur              | `gds.louvain.stream()` natif     |

---

### Conclusion

Pour les données **hautement connectées** (réseaux sociaux,
arbres de dépendances, routes, systèmes de recommandation),
Neo4j surpasse le relationnel sur trois axes :

- **Lisibilité :** le Cypher décrit visuellement le graphe —
  le pattern de la requête ressemble au schéma des données.

- **Performance :** les traversées de graphe évitent les JOINs
  coûteux. Chaque nœud stocke directement des pointeurs vers
  ses relations — la traversée est en **O(log N)** là où SQL
  ferait un scan de table.

- **Flexibilité :** ajouter un nouveau type de relation ne
  modifie pas le schéma des autres nœuds. Pas d'`ALTER TABLE`,
  pas de migration de données.

**SQL reste supérieur** pour les données tabulaires :
agrégations, rapports financiers, données sans relations
complexes entre entités.
```