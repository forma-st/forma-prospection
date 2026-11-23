-- Agent de prospection FORMA'ST — modèle de données de référence (PostgreSQL 15+)
-- Indépendant du framework : sert de contrat. Une implémentation Django est fournie dans models_django.py.
-- Cahier des charges : §5 (tables), §3.16 (messagerie), §3.17 (historique), §3.19 (colonnes IA).

CREATE EXTENSION IF NOT EXISTS pg_trgm;   -- dédoublonnage par nom
CREATE EXTENSION IF NOT EXISTS unaccent;

-- ---------- Comptes et contacts ----------
CREATE TABLE compte (
  id                 bigserial PRIMARY KEY,
  siren              char(9) UNIQUE,                 -- clé commune avec le CRM et l'outil AO (NULL tant que non rapproché)
  siret_siege        char(14),
  nom                text NOT NULL,
  nom_normalise      text NOT NULL,                  -- minuscules, sans accents ni forme juridique
  naf                varchar(6),
  segment            varchar(20),                    -- voir regles_metier.json > segments
  tranche_effectif   varchar(2),                     -- code INSEE
  effectif_estime    integer,
  nb_etablissements  integer DEFAULT 1,
  departement        varchar(3),
  ville              text,
  latitude           numeric(8,5),
  longitude          numeric(8,5),
  site_web           text,
  idcc               varchar(10),
  opco               text,
  icpe               boolean DEFAULT false,
  erp                boolean DEFAULT false,
  est_client         boolean DEFAULT false,          -- lu dans le CRM en mode crm_api
  statut             varchar(20) NOT NULL DEFAULT 'Nouveau',
  date_reprise       date,                           -- statut « Pas maintenant »
  responsable_id     bigint,                         -- utilisateur
  score              smallint,
  score_adequation   smallint,
  score_intention    smallint,
  score_acces        smallint,
  palier             char(1) CHECK (palier IN ('A','B','C')),
  explication_score  text,
  besoin             jsonb,                          -- {sst, sessions_sst, manutention, exercices, potentiel_an1, recurrent}
  decouverte         jsonb,                          -- réponses du guide d'appel
  provenance         jsonb NOT NULL DEFAULT '{}',    -- source par champ : {champ: {source, date, fichier}}
  crm_id             text,
  maj_sirene_le      timestamptz,
  cree_le            timestamptz NOT NULL DEFAULT now(),
  modifie_le         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX compte_nom_trgm ON compte USING gin (nom_normalise gin_trgm_ops);
CREATE INDEX compte_palier ON compte (palier, statut);

CREATE TABLE etablissement (
  id         bigserial PRIMARY KEY,
  compte_id  bigint NOT NULL REFERENCES compte ON DELETE CASCADE,
  siret      char(14) UNIQUE,
  adresse    text, code_postal varchar(5), ville text,
  latitude   numeric(8,5), longitude numeric(8,5),
  effectif   integer,
  actif      boolean DEFAULT true
);

CREATE TABLE contact (
  id                          bigserial PRIMARY KEY,
  compte_id                   bigint NOT NULL REFERENCES compte ON DELETE CASCADE,
  prenom text, nom text NOT NULL, fonction text,
  role_decision               varchar(15) CHECK (role_decision IN ('decideur','prescripteur','utilisateur','standard')),
  email                       text,
  statut_email                varchar(10) CHECK (statut_email IN ('verifie','probable','absent','invalide','bloque')),
  telephone                   text,
  linkedin_url                text,                  -- saisi à la main uniquement
  base_legale                 text NOT NULL DEFAULT 'interet_legitime_b2b',
  informe_le                  timestamptz,           -- information RGPD art. 14 (premier contact)
  oppose                      boolean NOT NULL DEFAULT false,
  dernier_contact_entrant_le  timestamptz,           -- départ du délai de conservation de 3 ans
  crm_id                      text
);
CREATE INDEX contact_email ON contact (lower(email));

-- ---------- Signaux et sources ----------
CREATE TABLE signal (
  id             bigserial PRIMARY KEY,
  compte_id      bigint NOT NULL REFERENCES compte ON DELETE CASCADE,
  type           varchar(20) NOT NULL,               -- voir regles_metier.json > signaux
  source         text NOT NULL,                      -- BODACC, France Travail, DECP, Veille AO…
  url            text,
  extrait        text NOT NULL,
  date_signal    date NOT NULL,
  poids          smallint NOT NULL,
  demi_vie_jours smallint NOT NULL,
  actif          boolean DEFAULT true,
  UNIQUE (compte_id, type, source, date_signal)
);

CREATE TABLE import_fichier (
  id                   bigserial PRIMARY KEY,
  nom_fichier          text NOT NULL,
  type                 varchar(20) NOT NULL,          -- prospects | historique
  correspondance       jsonb NOT NULL,                -- colonne du fichier -> champ
  lignes_lues integer, crees integer, mis_a_jour integer, doublons integer, rejets integer, opposes integer,
  rapport              jsonb,                         -- détail par ligne
  annulable_jusqu_au   timestamptz,
  importe_par_id       bigint,
  cree_le              timestamptz NOT NULL DEFAULT now()
);

-- ---------- Historique des formations (mode autonome ; lu dans le CRM en mode crm_api) ----------
CREATE TABLE historique_formation (
  id                 bigserial PRIMARY KEY,
  compte_id          bigint REFERENCES compte ON DELETE SET NULL,
  siren              char(9),
  etablissement_siret char(14),
  prestation         varchar(40) NOT NULL,            -- clé de regles_metier.json > echeances_historique_formations
  date_session       date NOT NULL,
  nb_stagiaires      integer NOT NULL,
  stagiaires         jsonb,                           -- données clients : jamais utilisées pour démarcher les stagiaires
  formateur          text,
  certificat_delivre boolean,
  echeance           date NOT NULL,                   -- calculée
  relance_creee      boolean DEFAULT false,
  source             varchar(20) NOT NULL,            -- import | saisie | crm | planif_st
  reference_planif_st text,
  crm_id             text
);
CREATE INDEX historique_echeance ON historique_formation (echeance) WHERE NOT relance_creee;

-- ---------- Séquences, messages, réponses ----------
CREATE TABLE sequence (
  id serial PRIMARY KEY, nom text NOT NULL, actif boolean DEFAULT true,
  mode_validation varchar(20) NOT NULL DEFAULT 'premier_envoi_valide',  -- brouillon | premier_envoi_valide | modele_valide
  plafond_par_boite_jour smallint DEFAULT 40
);
CREATE TABLE etape_sequence (
  id serial PRIMARY KEY, sequence_id int NOT NULL REFERENCES sequence ON DELETE CASCADE,
  ordre smallint NOT NULL, type varchar(10) NOT NULL CHECK (type IN ('email','linkedin','appel','tache','attente','condition')),
  delai_jours smallint NOT NULL, condition jsonb, modele text, consigne_ia text
);
CREATE TABLE inscription (
  id bigserial PRIMARY KEY, contact_id bigint NOT NULL REFERENCES contact ON DELETE CASCADE,
  sequence_id int NOT NULL REFERENCES sequence, etape_courante smallint DEFAULT 0,
  statut varchar(12) NOT NULL DEFAULT 'active',      -- active | pause | terminee | arretee
  prochaine_action_le timestamptz, arret_motif text,
  UNIQUE (contact_id, sequence_id)
);
CREATE TABLE boite_envoi (
  id serial PRIMARY KEY, adresse text UNIQUE NOT NULL,
  fournisseur varchar(10) NOT NULL CHECK (fournisseur IN ('graph','smtp')),
  plafond_jour smallint DEFAULT 40, montee_par_semaine smallint DEFAULT 5,
  etat varchar(10) DEFAULT 'ok', taux_rebond numeric(5,2), taux_plainte numeric(5,2)
);
CREATE TABLE message (
  id bigserial PRIMARY KEY, contact_id bigint REFERENCES contact ON DELETE SET NULL,
  boite_id int REFERENCES boite_envoi, canal varchar(10) NOT NULL, sens varchar(7) NOT NULL CHECK (sens IN ('sortant','entrant')),
  objet text, corps text NOT NULL, statut varchar(12) NOT NULL,   -- brouillon | programme | envoye | rebond | recu
  prevu_le timestamptz, envoye_le timestamptz, message_id_smtp text UNIQUE, en_reponse_a text,
  note_qualite smallint, valide_par_id bigint,
  generation jsonb                                   -- {modele_ia, cout_eur, consigne, sources}
);
CREATE TABLE reponse (
  id bigserial PRIMARY KEY, message_id bigint NOT NULL REFERENCES message ON DELETE CASCADE,
  classe varchar(25) NOT NULL, confiance smallint NOT NULL, extrait_ia jsonb,  -- {date_reprise, nouveau_contact, info}
  traitee boolean DEFAULT false, corrigee_par_id bigint
);

-- ---------- Tâches, automatisations, colonnes IA ----------
CREATE TABLE tache (
  id bigserial PRIMARY KEY, compte_id bigint REFERENCES compte ON DELETE CASCADE, contact_id bigint REFERENCES contact,
  type varchar(10) NOT NULL, titre text NOT NULL, texte_prepare text, canal varchar(10),
  echeance date NOT NULL, assignee_id bigint, faite_le timestamptz, reportee_au date, origine text
);
CREATE TABLE automatisation (
  id serial PRIMARY KEY, nom text NOT NULL, declencheur jsonb NOT NULL, conditions jsonb, actions jsonb NOT NULL,
  actif boolean DEFAULT false, simulation boolean DEFAULT true
);
CREATE TABLE execution_automatisation (
  id bigserial PRIMARY KEY, automatisation_id int REFERENCES automatisation, compte_id bigint,
  date timestamptz DEFAULT now(), resultat jsonb, annulable_jusqu_au timestamptz
);
CREATE TABLE niveau_autonomie (activite varchar(20) PRIMARY KEY, niveau varchar(10) NOT NULL CHECK (niveau IN ('manuel','proposer','auto')));
CREATE TABLE colonne_ia (id serial PRIMARY KEY, cle varchar(30) UNIQUE, question text NOT NULL, source_attendue text, actif boolean DEFAULT true);
CREATE TABLE valeur_ia (
  colonne_id int REFERENCES colonne_ia ON DELETE CASCADE, compte_id bigint REFERENCES compte ON DELETE CASCADE,
  valeur text, source text, calculee_le timestamptz DEFAULT now(), PRIMARY KEY (colonne_id, compte_id)
);
CREATE TABLE campagne (
  id serial PRIMARY KEY, mois date NOT NULL, titre text NOT NULL, segments text, canaux text,
  etat varchar(12) DEFAULT 'a_preparer', contenu jsonb, nb_destinataires integer
);

-- ---------- RGPD, coûts, journal ----------
CREATE TABLE opposition (id bigserial PRIMARY KEY, valeur text UNIQUE NOT NULL, type varchar(7) CHECK (type IN ('email','domaine','telephone')), source text, cree_le timestamptz DEFAULT now(), synchronise_crm_le timestamptz);
CREATE TABLE cout (id bigserial PRIMARY KEY, date timestamptz DEFAULT now(), nature varchar(15), objet text, fournisseur text, quantite numeric, montant_eur numeric(8,4), compte_id bigint);
CREATE TABLE journal (id bigserial PRIMARY KEY, date timestamptz DEFAULT now(), utilisateur_id bigint, acteur varchar(10) DEFAULT 'humain', action text NOT NULL, objet text, avant jsonb, apres jsonb, raison text);
CREATE TABLE file_sortante (id bigserial PRIMARY KEY, cible varchar(10) NOT NULL, evenement text NOT NULL, cle_idempotence text UNIQUE NOT NULL, charge jsonb NOT NULL, tentatives smallint DEFAULT 0, prochain_essai timestamptz DEFAULT now(), statut varchar(10) DEFAULT 'attente', erreur text);
