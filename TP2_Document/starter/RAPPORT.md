
# RAPPORT TP2 — MongoDB : Dossiers Médicaux HealthCare DZ

**Étudiant :** MESSAOUDI Abdelkrim  
**Module :** Bases de Données Avancées 

---

## 1. Choix de Modélisation

### Stratégie : Embedding vs Referencing

Deux patterns ont été utilisés selon la nature des données.

---

#### Pattern Embedding — Consultations dans le document Patient

```json
{
  "nom": "Bensalem",
  "consultations": [
    { "date": "...", "diagnostic": "HTA", "medicaments": [] }
  ]
}
```

**Justification :**  
Une consultation n'existe pas sans son patient. On lit toujours
les deux ensemble (afficher le dossier médical complet).
L'embedding évite une jointure et réduit la latence de lecture.
MongoDB conseille l'embedding quand la relation est **1-to-few**
et que les données sont accédées ensemble.

---

#### Pattern Referencing — Analyses dans une collection séparée

```json
{ "patient_id": ObjectId("..."), "type": "Glycémie", "resultat": {} }
```

**Justification :**  
Les analyses peuvent être nombreuses (des dizaines par patient)
et sont souvent consultées indépendamment (vue labo vs vue médecin).
Le referencing évite de dépasser la limite de **16 MB** par document
et permet de gérer le TTL d'archivage sur la collection séparément.

---

### Validation `$jsonSchema`

La validation garantit l'intégrité des données à l'insertion :

- **Champs obligatoires :** `cin`, `nom`, `prenom`, `dateNaissance`, `sexe`
- **Types stricts :** `date` pour les dates, `array` pour les listes
- **Enumération :** `sexe` ∈ {M, F} — `groupeSanguin` ∈ {A+, A−, B+, B−, AB+, AB−, O+, O−}

---

## 2. Pipelines d'Agrégation

### 3.1 — Distribution diagnostics par wilaya

```
$unwind consultations
  → $group (wilaya + diagnostic) → count
    → $sort count DESC
      → $limit 20
```

`$unwind` est nécessaire car les consultations sont un tableau embarqué.
Sans cette étape, on ne peut pas grouper sur leurs champs internes.

---

### 3.2 — Top médicament par spécialité

```
$unwind consultations → $unwind medicaments
  → $group (specialite + medicament) → count prescriptions
    → $sort → $group par specialite → $first (top 1)
```

Double `$unwind` car les médicaments sont un tableau dans un tableau.
Le second `$group` avec `$first` extrait le médicament le plus
prescrit après tri, sans avoir besoin de `$limit` par groupe.

---

### 3.3 — Évolution mensuelle

```
$unwind → $match (12 derniers mois)
  → $group (année + mois) → $sort chronologique
    → $project : concat "YYYY-MM"
```

`$dateDiff` est utilisé pour calculer l'âge dynamiquement
à partir de `$$NOW` plutôt qu'une valeur statique stockée.

---

### 3.4 — Patients à risque multiple

```
$match antecedents: { $all: ["Diabète type 2", "HTA"] }
  → $addFields age (dateDiff NOW)
    → $match age > 60
      → $sort nbAntecedents DESC
```

`$all` vérifie que **tous** les éléments du tableau sont présents,
contrairement à `$in` qui vérifie si **au moins un** est présent.

---

### 3.5 — Rapport médecins

```
$unwind → $group medecin
  → patientsUniques : $addToSet(_id)
  → totalConsultations : $sum(1)
    → $addFields tauxReconsultation
        = (total - nbUniques) / nbUniques × 100
          → $sort → $limit 5
```

`$addToSet` collecte les identifiants patients sans doublons,
permettant de distinguer *"50 consultations sur 10 patients"*
de *"50 consultations sur 50 patients différents"*.

---

## 3. Index et Optimisation

### Index créés

| Nom                    | Collection | Clé(s)                       | Type    | Objectif                       |
|------------------------|------------|------------------------------|---------|--------------------------------|
| idx_wilaya_antecedents | patients   | wilaya + antecedents         | Composé | Filtre géographique + médical  |
| idx_consultations_date | patients   | consultations.date           | Simple  | Requêtes temporelles           |
| idx_text_diagnostic    | patients   | consultations.diagnostic     | Text    | Recherche full-text            |
| idx_cin_unique         | patients   | cin                          | Unique  | Intégrité + recherche par CIN  |
| idx_analyses_patient   | analyses   | patient_id                   | Simple  | Jointures (`$lookup`)          |
| idx_ttl_analyses_5ans  | analyses   | date                         | TTL     | Archivage automatique 5 ans    |

---

### Comparaison `explain()` : avant / après index

| Métrique             | Sans index (COLLSCAN)      | Avec index (IXSCAN)       |
|----------------------|----------------------------|---------------------------|
| Stage                | COLLSCAN                   | IXSCAN                    |
| Documents examinés   | 20 (toute la collection)   | ≤ nb résultats            |
| Documents retournés  | n                          | n                         |
| Temps (ms)           | proportionnel à N          | quasi constant O(log N)   |

Avec 20 documents la différence est faible, mais sur **1 million**
de dossiers patients, le COLLSCAN examinerait 1 000 000 documents
quand l'IXSCAN n'en examinerait que quelques dizaines.

---

### Index TTL — Archivage automatique

```javascript
db.analyses.createIndex(
  { date: 1 },
  { expireAfterSeconds: 157680000 }  // 5 ans
)
```

MongoDB vérifie toutes les **60 secondes** les documents dont
`date + 5 ans < maintenant` et les supprime automatiquement.
Cela évite un job de nettoyage applicatif et maintient
la collection à taille maîtrisée sur le long terme.

---

## 4. Questions de Réflexion

### Q1 — Pourquoi avoir embarqué les consultations plutôt que les référencer ?

Les consultations sont intrinsèquement liées au patient :
on ne consulte jamais une consultation sans son patient.
L'embedding garantit la récupération du dossier complet
en **une seule lecture disque** (pas de jointure).

**Limite :** si un patient accumule des centaines de consultations
sur 30 ans, le document peut approcher la limite de 16 MB.
Dans ce cas, on peut archiver les consultations de plus de 5 ans
dans une collection séparée `consultations_archivees`.

---

### Q2 — Quel impact sur les performances si on référençait les consultations ?

Chaque affichage de dossier patient nécessiterait un `$lookup`
(équivalent d'un JOIN), soit **2 lectures disque** au lieu d'une.
Sur 10 000 consultations simultanées, cela doublerait la charge I/O.

En revanche, le référencement faciliterait les requêtes
portant uniquement sur les consultations
(ex : *"toutes les consultations de cardiologie ce mois"*)
sans avoir à `$unwind` des tableaux embarqués.

---

### Q3 — Comment gérer la croissance du document patient sur 10 ans ?

Trois stratégies complémentaires :

1. **Archivage par tranches temporelles** : déplacer les consultations
   de plus de 2 ans dans `consultations_archivees` avec le même
   `patient_id` comme référence.

2. **Bucket pattern** : un document par année de consultations.

```json
{ "patient_id": "...", "annee": 2023, "consultations": [] }
```

3. **Index TTL sur analyses** : déjà implémenté — suppression
   automatique après 5 ans pour les données de laboratoire.
```