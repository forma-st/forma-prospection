from datetime import date, timedelta
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone

from .models import (ActionLinkedIn, Compte, ConnexionLinkedIn, Contact, HistoriqueFormation, ImportFichier, Opposition,
                     Parametres, PublicationLinkedIn, Signal, Tache)
from .services import imports, qualite, redaction, rgpd
from .services.scoring import besoin, recalculer

EXEMPLE_CSV = """Raison sociale;SIRET;Code postal;Ville;Code APE;Effectif;Contact;Fonction;Email;Téléphone
ENTREPOTS DU PARISIS;93112233700013;95150;Taverny;5210B;180;Marion Caron;Responsable QSE;m.caron@parisis-entrepots.example;01 39 00 00 11
Logistique du Vexin SAS;91234567100015;95000;Cergy;5210B;240;Claire Vasseur;DRH;c.vasseur@logistique-vexin.example;
Clinique Saint-Roch-Val;93223344800012;78300;Poissy;8610Z;260;Paul Mercier;Directeur;p.mercier@gmail.com;
Hypermarchés Delta Nord;12345;59000;Lille;4711F;410;Anne Vidal;Responsable sécurité;a.vidal@deltanord.example;
Imprimerie Lumière;93334455800012;76000;Rouen;1812Z;35;Hugo Blanc;Gérant;h.blanc@imprimerie-lumiere.example;02 35 00 00 22
BTP Exemple Est;93445566800012;77100;Meaux;4399C;90;Marc Dupuis;Conducteur de travaux;m.dupuis@exemple-btp.example;
Résidence Les Charmilles;93556677800012;95100;Argenteuil;8710A;120;Lucie Perrot;Directrice;l.perrot@charmilles.example;01 34 00 00 33
Transports Martin & Cie;93667788900011;94150;Rungis;4941A;75;;;;01 45 00 00 44
"""


def vexin():
    """Même prospect que la maquette : palier A, score 89."""
    c = Compte.objects.create(nom="Logistique du Vexin", siren="912345671", code_postal="95000", ville="Cergy", segment="logistique",
                              naf="52.10B", effectif=240, nb_etablissements=2, icpe=True, source="Fichier CCI 2026")
    today = timezone.localdate()
    Signal.objects.create(compte=c, type="qse", texte="Offre d'emploi « Responsable HSE (CDI) »", source="France Travail", date_signal=today - timedelta(days=6))
    Signal.objects.create(compte=c, type="site", texte="Nouvel établissement immatriculé", source="BODACC", date_signal=today - timedelta(days=25))
    Contact.objects.create(compte=c, prenom="Claire", nom="Vasseur", fonction="Directrice des ressources humaines", role="decideur",
                           email="c.vasseur@logistique-vexin.example", statut_email="verifie")
    Contact.objects.create(compte=c, nom="Standard", fonction="Accueil", role="standard", email="contact@logistique-vexin.example",
                           statut_email="verifie", telephone="01 30 00 00 01")
    return recalculer(c)


class ScoreEtBesoin(TestCase):
    def test_score_identique_a_la_maquette(self):
        c = vexin()
        self.assertEqual((c.score_adequation, c.score_intention, c.score_accessibilite, c.score, c.palier), (95, 84, 85, 89, "A"))
        self.assertIn("nouvel établissement il y a 25 j", c.explication.lower())

    def test_besoin(self):
        b = besoin(vexin(), part_sst=12)
        self.assertEqual((b["sst"], b["sessions_sst"], b["manutention"], b["exercices"]), (29, 3, 144, 4))
        self.assertFalse(b["opco_finance"])

    def test_signal_ancien_perd_sa_valeur(self):
        c = vexin()
        Signal.objects.filter(compte=c).update(date_signal=timezone.localdate() - timedelta(days=400))
        self.assertLess(recalculer(c).score_intention, 5)

    def test_parametres_changent_le_palier(self):
        c = vexin()
        p = Parametres.get()
        p.seuil_palier_a = 95
        p.save()
        self.assertEqual(recalculer(c, p).palier, "B")


class Echeances(TestCase):
    def test_mac_sst_a_24_mois_et_fin_de_mois(self):
        h = HistoriqueFormation(nom_client="X", prestation="MAC SST", date_session=date(2025, 1, 20))
        self.assertEqual(h.echeance, date(2027, 1, 20))
        h2 = HistoriqueFormation(nom_client="X", prestation="Exercice d'évacuation", date_session=date(2026, 8, 31))
        self.assertEqual(h2.echeance, date(2027, 2, 28))

    def test_etat(self):
        today = timezone.localdate()
        self.assertEqual(HistoriqueFormation(nom_client="X", prestation="MAC SST", date_session=today - timedelta(days=700)).etat, "relancer")
        self.assertEqual(HistoriqueFormation(nom_client="X", prestation="MAC SST", date_session=today - timedelta(days=800)).etat, "retard")
        self.assertEqual(HistoriqueFormation(nom_client="X", prestation="MAC SST", date_session=today - timedelta(days=100)).etat, "ok")


class Opposition_(TestCase):
    def test_domaine_et_adresse(self):
        c = vexin()
        n = rgpd.enregistrer_opposition("@Logistique-Vexin.example")
        self.assertEqual(n, 2)
        self.assertTrue(rgpd.est_oppose("c.vasseur@logistique-vexin.example"))
        self.assertTrue(rgpd.est_oppose("AUTRE@logistique-vexin.example"))
        self.assertFalse(rgpd.est_oppose("x@ailleurs.example"))
        self.assertEqual(recalculer(c).score_accessibilite, 0)


class Imports(TestCase):
    def test_luhn(self):
        self.assertTrue(imports.luhn("93112233700013"))
        self.assertTrue(imports.luhn("931 122 337"))
        self.assertFalse(imports.luhn("12345"))
        self.assertFalse(imports.luhn("93112233700014"))

    def test_lecture_et_correspondance(self):
        entetes, lignes = imports.lire_fichier("x.csv", EXEMPLE_CSV.encode("cp1252"))
        self.assertEqual(len(lignes), 8)
        self.assertEqual(imports.deviner_correspondance(entetes),
                         ["nom", "siret", "code_postal", "ville", "naf", "effectif", "contact", "fonction", "email", "telephone"])

    def test_analyse_comme_la_maquette(self):
        vexin()
        Opposition.objects.create(valeur="m.dupuis@exemple-btp.example")
        entetes, lignes = imports.lire_fichier("x.csv", EXEMPLE_CSV.encode())
        imp = ImportFichier.objects.create(nom_fichier="x.csv", entetes=entetes, lignes=lignes, correspondance=imports.deviner_correspondance(entetes))
        etats = [x["etat"] for x in imports.analyser(imp)]
        self.assertEqual(etats, ["Nouveau", "Doublon", "À vérifier", "À vérifier", "Nouveau", "Opposé", "Nouveau", "Nouveau"])
        r = imports.appliquer(imp)
        self.assertEqual((r["crees"], r["completes"]), (6, 1))
        self.assertFalse(Compte.objects.filter(nom__icontains="BTP Exemple").exists())
        parisis = Compte.objects.get(nom="Entrepots Du Parisis")
        self.assertEqual((parisis.siren, parisis.segment, parisis.naf), ("931122337", "logistique", "52.10B"))
        self.assertEqual(Compte.objects.get(nom__startswith="Clinique").contacts.get().email, "")  # e-mail personnel écarté
        self.assertEqual(imports.annuler(imp), 6)
        self.assertTrue(Compte.objects.filter(nom="Logistique du Vexin").exists())


class Redaction(TestCase):
    def test_tous_les_canaux(self):
        c = vexin()
        k = c.contact_principal()
        mail = redaction.generer(c, k, "email")
        self.assertIn("Claire Vasseur", mail["texte"])
        self.assertIn("ne plus recevoir", mail["texte"])
        q = qualite.controler(mail["texte"], "email", c)
        self.assertTrue(all(ok for ok, l in q["controles"] if "crochets" not in l and "compléter" not in l), q)
        self.assertLessEqual(len(redaction.generer(c, k, "linkedin")["texte"]), 300)
        self.assertIn("OBJECTIONS", redaction.generer(c, k, "appel")["texte"])
        self.assertIn("ne plus recevoir", redaction.generer(c, k, "relance")["texte"])
        self.assertIsNone(qualite.controler("x", "appel"))

    def test_mots_interdits(self):
        q = qualite.controler("Bonjour, offre gratuite et urgente !! ? ?", "email")
        self.assertLess(q["note"], 60)


class Ecrans(TestCase):
    def setUp(self):
        self.u = User.objects.create_user("julie", password="x", is_staff=True, is_superuser=True)
        self.client.force_login(self.u)
        self.c = vexin()

    def test_toutes_les_pages(self):
        HistoriqueFormation.objects.create(nom_client="Client", prestation="MAC SST", date_session=timezone.localdate() - timedelta(days=700))
        for url in ["/prospection/", "/prospection/prospects/", "/prospection/prospects/?vue=A", "/prospection/prospects/?vue=sanscontact",
                    f"/prospection/compte/{self.c.pk}/", f"/prospection/compte/{self.c.pk}/?canal=linkedin", f"/prospection/compte/{self.c.pk}/?canal=appel",
                    f"/prospection/compte/{self.c.pk}/?canal=relance", "/prospection/import/", "/prospection/historique/", "/prospection/taches/",
                    "/prospection/opposition/", "/prospection/compte/nouveau/"]:
            self.assertEqual(self.client.get(url).status_code, 200, url)
        self.assertEqual(self.client.get("/prospection/linkedin/").status_code, 404)  # option désactivée

    def test_import_par_l_ecran(self):
        r = self.client.post("/prospection/import/", {"type": "prospects", "fichier": SimpleUploadedFile("base.csv", EXEMPLE_CSV.encode())})
        imp = ImportFichier.objects.get()
        self.assertRedirects(r, f"/prospection/import/{imp.pk}/")
        self.assertContains(self.client.get(r.url), "Importer 7 lignes et compléter 1 fiche")
        data = {f"col{i}": v for i, v in enumerate(imp.correspondance)} | {"appliquer": "1"}
        self.client.post(r.url, data)
        self.assertEqual(Compte.objects.count(), 8)
        self.assertEqual(Compte.objects.get(nom="Logistique du Vexin").contacts.count(), 2)  # doublon : pas de second « Claire Vasseur »

    def test_import_historique_et_relances(self):
        csv = "SIREN;Raison sociale;Prestation;Date de session;Nombre de stagiaires\n912345671;Logistique du Vexin;MAC SST;" + \
              (timezone.localdate() - timedelta(days=700)).strftime("%d/%m/%Y") + ";12\n;Client B;Gestes et postures;2026-01-05;8\n;Client C;Inconnue;2026-01-05;8\n"
        self.client.post("/prospection/import/", {"type": "historique", "fichier": SimpleUploadedFile("h.csv", csv.encode())})
        imp = ImportFichier.objects.get()
        self.client.post(f"/prospection/import/{imp.pk}/", {f"col{i}": v for i, v in enumerate(imp.correspondance)} | {"appliquer": "1"})
        self.assertEqual(HistoriqueFormation.objects.count(), 2)
        h = HistoriqueFormation.objects.get(nom_client="Logistique du Vexin")
        self.assertEqual(h.compte, self.c)
        self.client.post("/prospection/historique/relancer/", {})
        self.assertTrue(Tache.objects.filter(titre__contains="MAC SST").exists())
        self.assertTrue(self.c.signaux.filter(type="mac").exists())

    def test_journee_fait_et_demain(self):
        t = Tache.objects.create(compte=self.c, titre="Appeler Claire", echeance=timezone.localdate())
        self.assertContains(self.client.get("/prospection/"), "Appeler Claire")
        self.client.post("/prospection/journee/action/", {"cle": f"t{t.pk}", "quoi": "demain"})
        self.assertNotContains(self.client.get("/prospection/"), "Appeler Claire")
        t2 = Tache.objects.create(compte=self.c, titre="Relancer Claire", echeance=timezone.localdate())
        self.client.post("/prospection/journee/action/", {"cle": f"t{t2.pk}", "quoi": "fait"})
        t2.refresh_from_db()
        self.assertIsNotNone(t2.faite_le)

    def test_envoi_note_et_bloque_si_oppose(self):
        k = self.c.contact_principal()
        self.client.post(f"/prospection/compte/{self.c.pk}/action/", {"action": "envoye", "canal": "email", "contact_id": k.pk, "objet": "x", "texte": "y", "relance": "5"})
        self.c.refresh_from_db()
        k.refresh_from_db()
        self.assertEqual(self.c.statut, "En contact")
        self.assertIsNotNone(k.informe_le)
        self.assertTrue(Tache.objects.filter(titre__startswith="Relancer").exists())
        self.client.post(f"/prospection/compte/{self.c.pk}/action/", {"action": "opposer"})
        self.c.refresh_from_db()
        self.assertEqual(self.c.statut, "Opposé")
        self.assertTrue(rgpd.est_oppose(k.email))

    def test_redirection_externe_refusee(self):
        r = self.client.post(f"/prospection/compte/{self.c.pk}/action/", {"action": "note", "texte": "x", "retour": "https://ailleurs.example/"})
        self.assertEqual(r.url, f"/prospection/compte/{self.c.pk}/")

    def test_ajout_contact_oppose_refuse(self):
        Opposition.objects.create(valeur="@bloque.example")
        self.client.post(f"/prospection/compte/{self.c.pk}/action/", {"action": "contact", "nom": "Test", "email": "a@bloque.example"})
        self.assertFalse(Contact.objects.filter(nom="Test").exists())


class FauxHttp:
    def __init__(self, reponses):
        self.reponses, self.appels = reponses, []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def post(self, url, **kw):
        self.appels.append(("POST", url, kw))
        return self.reponses.pop(0)

    def get(self, url, **kw):
        self.appels.append(("GET", url, kw))
        return self.reponses.pop(0)


def rep(code, data=None, headers=None):
    return SimpleNamespace(status_code=code, json=lambda: data or {}, text=str(data), headers=headers or {})


@override_settings(BASE_URL="https://prospection.example")
@mock.patch.dict("os.environ", {"LINKEDIN_CLIENT_ID": "cid", "LINKEDIN_CLIENT_SECRET": "secret"})
class LinkedIn(TestCase):
    def setUp(self):
        self.u = User.objects.create_user("julie", password="x")
        self.client.force_login(self.u)
        p = Parametres.get()
        p.linkedin_actif = True
        p.save()
        self.c = vexin()

    def test_connexion_complete(self):
        r = self.client.get("/prospection/linkedin/connecter/")
        self.assertTrue(r.url.startswith("https://www.linkedin.com/oauth/v2/authorization?"))
        self.assertIn("client_id=cid", r.url)
        self.assertIn("w_member_social", r.url)
        etat = self.client.session["linkedin_etat"]
        faux = FauxHttp([rep(200, {"access_token": "tok", "expires_in": 5184000, "scope": "openid,profile,email,w_member_social"}),
                         rep(200, {"sub": "abc123", "name": "Julie Morel", "email": "julie@formast.example"})])
        with mock.patch("prospection.services.linkedin._client", return_value=faux):
            self.client.get("/prospection/linkedin/retour/", {"code": "c0de", "state": etat})
        cx = ConnexionLinkedIn.objects.get()
        self.assertEqual((cx.sub, cx.nom, cx.peut_publier, cx.valide), ("abc123", "Julie Morel", True, True))
        self.assertEqual(faux.appels[0][2]["data"]["redirect_uri"], "https://prospection.example/prospection/linkedin/retour/")

    def test_etat_falsifie_refuse(self):
        self.client.get("/prospection/linkedin/connecter/")
        self.client.get("/prospection/linkedin/retour/", {"code": "x", "state": "faux"})
        self.assertFalse(ConnexionLinkedIn.objects.exists())

    def test_publication(self):
        ConnexionLinkedIn.objects.create(utilisateur=self.u, sub="abc123", nom="J", jeton="tok", expire_le=timezone.now() + timedelta(days=30),
                                         portees="openid profile email w_member_social")
        faux = FauxHttp([rep(201, headers={"x-restli-id": "urn:li:share:1"})])
        with mock.patch("prospection.services.linkedin._client", return_value=faux):
            self.client.post("/prospection/linkedin/publier/", {"texte": "Bonjour LinkedIn", "quoi": "publier"})
        pub = PublicationLinkedIn.objects.get()
        self.assertEqual((pub.statut, pub.urn), ("publiee", "urn:li:share:1"))
        _, url, kw = faux.appels[0]
        self.assertEqual(url, "https://api.linkedin.com/rest/posts")
        self.assertEqual(kw["json"]["author"], "urn:li:person:abc123")
        self.assertIn("LinkedIn-Version", kw["headers"])

    def test_erreur_de_publication_gardee(self):
        ConnexionLinkedIn.objects.create(utilisateur=self.u, sub="a", jeton="t", expire_le=timezone.now() + timedelta(days=1), portees="w_member_social")
        with mock.patch("prospection.services.linkedin._client", return_value=FauxHttp([rep(403, {"message": "refusé"})])):
            self.client.post("/prospection/linkedin/publier/", {"texte": "x", "quoi": "publier"})
        self.assertEqual(PublicationLinkedIn.objects.get().statut, "erreur")

    def test_panneau_et_plafonds(self):
        r = self.client.get(f"/prospection/compte/{self.c.pk}/")
        self.assertContains(r, "Invitation préparée")
        self.assertContains(r, "linkedin.com/search/results/companies")
        p = Parametres.get()
        p.linkedin_invitations_semaine = 2
        p.save()
        for _ in range(2):
            self.client.post(f"/prospection/compte/{self.c.pk}/action/", {"action": "linkedin", "type": "invitation"})
        self.assertEqual(ActionLinkedIn.objects.filter(type="invitation").count(), 2)
        self.assertContains(self.client.get(f"/prospection/compte/{self.c.pk}/"), "Plafond atteint")
        self.assertEqual(self.client.get("/prospection/linkedin/").status_code, 200)


class Autonomie(TestCase):
    """L'outil fonctionne seul, et se relie à FORM'AO seulement si on le configure."""

    def setUp(self):
        self.u = User.objects.create_user("julie", password="x", is_staff=True, is_superuser=True)

    def test_connexion_et_racine(self):
        self.assertRedirects(self.client.get("/prospection/"), "/connexion/?next=/prospection/")
        self.assertContains(self.client.get("/connexion/"), "Se connecter")
        r = self.client.post("/connexion/", {"username": "julie", "password": "x"})
        self.assertRedirects(r, "/prospection/")
        self.assertRedirects(self.client.get("/"), "/prospection/", fetch_redirect_response=False)

    def test_catalogue_d_exemple_puis_reel(self):
        from .models import Prestation
        from .services.scoring import tarifs
        self.assertEqual(tarifs()["source"], "exemple")
        Prestation.objects.filter(usage_potentiel="sst").update(prix_intra_ht=1600, exemple=False)
        Prestation.objects.filter(exemple=True).update(actif=False)
        t = tarifs()
        self.assertEqual((t["sst"], t["source"]), (1600.0, "catalogue"))

    def test_formao_non_configure(self):
        self.client.force_login(self.u)
        r = self.client.post("/prospection/import/acheteurs-ao/", follow=True)
        self.assertContains(r, "n&#x27;est pas configurée")
        self.assertContains(self.client.get("/prospection/import/"), "FORMAO_URL")

    @override_settings(FORMAO_URL="http://formao.example", FORMAO_JETON="jeton")
    def test_formao_acheteurs_et_catalogue(self):
        self.client.force_login(self.u)
        reponses = {
            "acheteurs": {"resultats": [{"nom": "Ville de Pontoise (exemple)", "siren": "219500500", "departement": "95",
                                         "avis": [{"objet": "Formation SST des agents", "url": "https://formao.example/avis/1", "date_publication": "2026-11-02"}]}]},
            "profil": {"nom": "FORMA'ST", "presentation": "Organisme de formation", "references_citables": ["Enseigne nationale"]},
            "catalogue": {"resultats": [{"id": 7, "intitule": "Sauveteur secouriste du travail", "categorie": "SECOURISME", "prix_intra_ht": 1500, "actif": True}]},
        }
        def faux_get(url, **kw):
            self.assertEqual(kw["headers"]["Authorization"], "Bearer jeton")
            return SimpleNamespace(status_code=200, json=lambda: reponses[url.rsplit("/", 1)[1]])
        with mock.patch("prospection.services.formao.httpx.get", side_effect=faux_get):
            self.client.post("/prospection/import/acheteurs-ao/")
            self.client.post("/prospection/import/acheteurs-ao/")  # pas de doublon
            self.client.post("/prospection/formao/synchroniser/")
        c = Compte.objects.get(siren="219500500")
        self.assertEqual((c.segment, c.signaux.count(), Compte.objects.count()), ("collectivite", 1, 1))
        from .models import Prestation, ProfilEntreprise
        from .services.scoring import tarifs
        self.assertIn("Enseigne nationale", ProfilEntreprise.get().texte_pour_ia())
        self.assertEqual(Prestation.objects.get(reference_formao="7").usage_potentiel, "sst")
        self.assertEqual((tarifs()["sst"], tarifs()["source"]), (1500.0, "catalogue"))

    @override_settings(FORMAO_URL="http://formao.example", FORMAO_JETON="mauvais")
    def test_formao_jeton_refuse(self):
        self.client.force_login(self.u)
        with mock.patch("prospection.services.formao.httpx.get", return_value=SimpleNamespace(status_code=401, json=dict)):
            r = self.client.post("/prospection/import/acheteurs-ao/", follow=True)
        self.assertContains(r, "refuse le jeton")


# ---------------------------------------------------------------------------- Phase 2

from datetime import datetime  # noqa: E402

from .models import BoiteEnvoi, EtapeSequence, Inscription, Message, Sequence  # noqa: E402
from .services import messagerie, reponses, sequences  # noqa: E402


def paris(*a):
    return timezone.make_aware(datetime(*a))


class FauxSMTP:
    def __init__(self):
        self.envoyes = []

    def send_message(self, e):
        self.envoyes.append(e)


class Phase2(TestCase):
    def setUp(self):
        self.u = User.objects.create_user("julie", password="x", is_staff=True, is_superuser=True)
        self.c = vexin()
        self.k = self.c.contacts.get(nom="Vasseur")
        self.boite = BoiteEnvoi.objects.create(nom="Julie", adresse="julie@formast.example", smtp_hote="smtp.example", utilisateur=self.u)
        p = Parametres.get()
        p.adresse_test = "test@formast.example"
        p.save()
        self.seq = Sequence.objects.get(nom="Ouverture de site")  # livrée par défaut (5 étapes, premier e-mail validé)

    def test_creneaux(self):
        self.assertEqual(messagerie.prochain_creneau(paris(2026, 11, 21, 10, 0)), paris(2026, 11, 23, 8, 30))  # samedi → lundi
        self.assertEqual(messagerie.prochain_creneau(paris(2026, 11, 18, 12, 0)), paris(2026, 11, 18, 14, 0))  # pause de midi
        self.assertEqual(messagerie.prochain_creneau(paris(2026, 11, 18, 18, 0)), paris(2026, 11, 19, 8, 30))
        self.assertTrue(messagerie.dans_les_plages(paris(2026, 11, 18, 9, 0)))
        self.assertFalse(messagerie.dans_les_plages(paris(2026, 11, 22, 9, 0)))

    def test_inscription_refusee(self):
        sequences.inscrire(self.seq, self.k, self.u)
        with self.assertRaises(sequences.InscriptionImpossible):
            sequences.inscrire(self.seq, self.k, self.u)  # déjà en cours
        sans = Contact.objects.create(compte=self.c, nom="Sans mail", role="decideur")
        with self.assertRaises(sequences.InscriptionImpossible):
            sequences.inscrire(self.seq, sans, self.u)
        Opposition.objects.create(valeur="@autre.example")
        o = Contact.objects.create(compte=self.c, nom="Opposé", email="x@autre.example")
        with self.assertRaises(sequences.InscriptionImpossible):
            sequences.inscrire(self.seq, o, self.u)

    def test_sequence_complete_en_mode_test(self):
        ins = sequences.inscrire(self.seq, self.k, self.u)
        self.c.refresh_from_db()
        self.assertEqual(self.c.statut, "En contact")
        t0 = messagerie.prochain_creneau(timezone.now() + timedelta(minutes=1))
        sequences.avancer(t0)
        m1 = Message.objects.get(inscription=ins)
        self.assertEqual(m1.statut, "a_valider")  # premier e-mail validé
        self.assertIn("ne plus recevoir", m1.corps)
        messagerie.programmer(m1, self.u, quand=t0)
        smtp = FauxSMTP()
        self.assertEqual(messagerie.traiter_file(t0, connexion=smtp)["envoyes"], 1)
        e = smtp.envoyes[0]
        self.assertEqual(e["To"], "test@formast.example")  # mode test par défaut
        self.assertTrue(e["Subject"].startswith("[TEST → c.vasseur@logistique-vexin.example]"))
        self.assertIn("mailto:julie@formast.example", e["List-Unsubscribe"])
        with self.assertRaises(messagerie.EnvoiImpossible):
            messagerie.envoyer(Message.objects.get(pk=m1.pk), connexion=smtp)  # jamais deux fois
        sequences.avancer(t0 + timedelta(days=2, minutes=1))  # J+2 : LinkedIn
        self.assertTrue(Tache.objects.filter(type="linkedin", contact=self.k).exists())
        sequences.avancer(t0 + timedelta(days=5, minutes=2))  # J+5 : appel
        self.assertTrue(Tache.objects.filter(type="appel", contact=self.k).exists())
        sequences.avancer(t0 + timedelta(days=9, minutes=3))  # J+9 : relance automatique
        m2 = Message.objects.filter(inscription=ins).exclude(pk=m1.pk).get()
        self.assertEqual(m2.statut, "programme")
        self.assertEqual(m2.en_reponse_a, Message.objects.get(pk=m1.pk).message_id)

    def test_opposition_et_plafond_au_dernier_moment(self):
        m = Message.objects.create(compte=self.c, contact=self.k, boite=self.boite, destinataire=self.k.email, objet="x", corps="y", statut="programme", prevu_le=timezone.now())
        rgpd.enregistrer_opposition(self.k.email)
        with self.assertRaises(messagerie.EnvoiImpossible):
            messagerie.envoyer(m, connexion=FauxSMTP())
        self.assertEqual(Message.objects.get(pk=m.pk).statut, "annule")
        self.boite.plafond_jour = 0
        self.boite.save()
        autre = Contact.objects.create(compte=self.c, nom="Autre", email="autre@x.example")
        m2 = Message.objects.create(compte=self.c, contact=autre, boite=self.boite, destinataire=autre.email, objet="x", corps="y", statut="programme")
        with self.assertRaisesMessage(messagerie.EnvoiImpossible, "Plafond"):
            messagerie.envoyer(m2, connexion=FauxSMTP())

    def test_envoi_reel(self):
        p = Parametres.get()
        p.mode_test = False
        p.save()
        m = Message.objects.create(compte=self.c, contact=self.k, boite=self.boite, destinataire=self.k.email, objet="Bonjour", corps="Texte", statut="programme")
        smtp = FauxSMTP()
        messagerie.envoyer(m, connexion=smtp)
        self.assertEqual(smtp.envoyes[0]["To"], self.k.email)
        self.k.refresh_from_db()
        self.assertIsNotNone(self.k.informe_le)

    def _reponse(self, texte, objet="RE: Formation", en_reponse_a="", expediteur=None, entetes=""):
        brut = (f"From: Claire Vasseur <{expediteur or self.k.email}>\r\nTo: julie@formast.example\r\nSubject: {objet}\r\n"
                f"Message-ID: <rep{Message.objects.count()}@client.example>\r\n" + (f"In-Reply-To: {en_reponse_a}\r\n" if en_reponse_a else "") + entetes +
                "Content-Type: text/plain; charset=utf-8\r\n\r\n" + texte).encode("utf-8")
        return reponses.enregistrer(self.boite, brut)

    def test_reponse_interessee_arrete_la_sequence(self):
        ins = sequences.inscrire(self.seq, self.k, self.u)
        envoye = Message.objects.create(compte=self.c, contact=self.k, boite=self.boite, inscription=ins, destinataire=self.k.email, objet="x", corps="y",
                                        statut="envoye", message_id="<orig@formast.example>")
        r = self._reponse("Bonjour, oui cela nous intéresse, appelez-moi jeudi.\n\n> message d'origine", en_reponse_a="<orig@formast.example>")
        self.assertEqual((r.classe, r.en_reponse_a), ("interesse", envoye.message_id))
        ins.refresh_from_db()
        self.c.refresh_from_db()
        self.assertEqual((ins.statut, self.c.statut), ("arretee", "A répondu"))
        self.assertTrue(Tache.objects.filter(titre__startswith="Rappeler").exists())

    def test_reponses_automatiques(self):
        ins = sequences.inscrire(self.seq, self.k, self.u)
        r = self._reponse("Je suis absent jusqu'au 25/11 inclus.", objet="Réponse automatique", entetes="Auto-Submitted: auto-replied\r\n")
        self.assertEqual(r.classe, "absence")
        ins.refresh_from_db()
        self.assertEqual(ins.statut, "pause")
        r2 = self._reponse("Merci de ne plus m'écrire.")
        self.assertEqual(r2.classe, "opposition")
        self.assertTrue(rgpd.est_oppose(self.k.email))
        self.assertIsNone(self._reponse("Bonjour", expediteur="inconnu@ailleurs.example"))  # sans rapport : ignoré

    def test_classement_et_date_de_reprise(self):
        self.assertEqual(reponses.classer("Pas pour le moment, revenez vers moi en mars.")[0], "pas_maintenant")
        self.assertEqual(reponses.date_reprise("revenez en mars", date(2026, 11, 18)), date(2027, 3, 1))
        self.assertEqual(reponses.classer("Voyez avec M. Perrin, notre responsable sécurité.")[0], "mauvais_interlocuteur")
        self.assertEqual(reponses.classer("Nous travaillons déjà avec un organisme.")[0], "deja_equipe")
        self.assertEqual(reponses.classer("STOP")[0], "opposition")
        self.assertEqual(reponses.classer("Merci pour votre message.")[0], "autre")

    def test_ecrans(self):
        self.client.force_login(self.u)
        for url in ["/prospection/sequences/", f"/prospection/sequences/{self.seq.pk}/", "/prospection/messagerie/", "/prospection/reponses/",
                    "/prospection/statistiques/", "/prospection/prospects/?affichage=colonnes", f"/prospection/compte/{self.c.pk}/"]:
            self.assertEqual(self.client.get(url).status_code, 200, url)
        self.assertContains(self.client.get("/prospection/"), "Forma Prospect")
        r = self.client.post("/prospection/sequences/inscrire/", {"sequence": self.seq.pk, "compte": [self.c.pk], "retour": "/prospection/prospects/"})
        self.assertRedirects(r, "/prospection/prospects/", fetch_redirect_response=False)
        self.assertTrue(Inscription.objects.filter(contact=self.k, statut="active").exists())
        self.client.post(f"/prospection/compte/{self.c.pk}/envoyer/", {"contact_id": self.k.pk, "objet": "Bonjour", "texte": "Texte\n[Prénom Nom]", "relance": "5"})
        m = Message.objects.get(objet="Bonjour")
        self.assertEqual(m.statut, "programme")
        self.client.post("/prospection/messagerie/", {"action": "annuler", "message_id": m.pk})
        self.assertEqual(Message.objects.get(pk=m.pk).statut, "annule")
        with mock.patch("prospection.services.messagerie._smtp") as s:
            s.return_value.__enter__.return_value = FauxSMTP()
            m3 = Message.objects.create(compte=self.c, contact=self.k, boite=self.boite, destinataire=self.k.email, objet="À valider", corps="z")
            self.client.post("/prospection/messagerie/", {"action": "envoyer", "message_id": m3.pk, "objet": "À valider", "corps": "z"})
        self.assertEqual(Message.objects.get(pk=m3.pk).statut, "envoye")


# ---------------------------------------------------------------------------- Phase 3 : recherche automatique

from .models import ExecutionRecherche, RechercheAuto  # noqa: E402
from .services import recherche  # noqa: E402


def entreprise(siren, nom, naf="52.10B", tranche="22", sites=2, cp="95000", dep="95", etat="A"):
    return {"siren": siren, "nom_complet": nom, "activite_principale": naf, "tranche_effectif_salarie": tranche, "nombre_etablissements_ouverts": sites,
            "etat_administratif": etat, "siege": {"siret": siren + "00011", "code_postal": cp, "departement": dep, "libelle_commune": "CERGY",
                                                  "activite_principale": naf, "latitude": "49.03", "longitude": "2.06"}, "complements": {"liste_idcc": ["16"]}}


@mock.patch("prospection.services.recherche.time.sleep", lambda s: None)
class RechercheAutomatique(TestCase):
    def setUp(self):
        self.r = RechercheAuto.objects.get(nom__startswith="Logistique et entreposage")  # livrée par défaut

    def test_outils(self):
        self.assertEqual(recherche.tranches_depuis(50)[0], "21")
        self.assertEqual(recherche.tranches_depuis(50, 2000), ["21", "22", "31", "32", "41", "42"])
        self.assertTrue(recherche.correspond_naf("10.13A", ["10"]))
        self.assertFalse(recherche.correspond_naf("20.16Z", ["10", "52.10B"]))
        self.assertEqual(recherche.section_de("22"), "C")
        self.assertEqual(RechercheAuto.objects.count(), 10)

    def test_sirene_filtre_et_dedoublonne(self):
        page = {"results": [entreprise("111111118", "ENTREPOTS DU NORD"), entreprise("222222226", "FERMEE SA", etat="C"),
                            entreprise("333333334", "PETITE LOGISTIQUE", tranche="12")], "total_pages": 1}
        with mock.patch("prospection.services.recherche.get_json", return_value=page) as g:
            ex = recherche.executer(self.r)
            params = g.call_args.kwargs["params"]
        self.assertIn("52.10B", params["activite_principale"])
        self.assertNotIn("departement", params)  # France entière
        self.assertEqual((ex.examines, ex.crees, ex.erreur), (3, 1, ""))
        c = Compte.objects.get(siren="111111118")
        self.assertEqual((c.statut, c.segment, c.ville), ("À qualifier", "logistique", "Cergy"))
        self.assertTrue(c.source.startswith("Recherche auto"))
        with mock.patch("prospection.services.recherche.get_json", return_value=page):
            self.assertEqual(recherche.executer(self.r).crees, 0)  # déjà connu

    def test_palier_minimum(self):
        self.r.palier_min = "A"
        self.r.save()
        page = {"results": [entreprise("111111118", "ENTREPOTS DU SUD", cp="13000", dep="13", sites=1)], "total_pages": 1}
        with mock.patch("prospection.services.recherche.get_json", return_value=page):
            ex = recherche.executer(self.r)
        self.assertEqual((ex.crees, ex.ignores), (0, 1))
        self.assertFalse(Compte.objects.exists())

    def test_bodacc_signal_et_creation(self):
        connu = Compte.objects.create(nom="Déjà connu", siren="444444442", segment="logistique", effectif=200)
        r = RechercheAuto.objects.get(source="bodacc")
        annonces = {"results": [{"registre": ["444 444 442", "444444442"], "dateparution": "2026-11-20", "ville": "Roissy"},
                                {"registre": ["111 111 118"], "dateparution": "2026-11-19", "numerodepartement": "95"}]}
        def faux(url, params=None):
            if "bodacc" in url:
                return annonces if params.get("offset", 0) == 0 else {"results": []}
            return {"results": [entreprise("111111118", "NOUVEL ENTREPOT")]}
        with mock.patch("prospection.services.recherche.get_json", side_effect=faux):
            ex = recherche.executer(r)
        self.assertEqual((ex.signaux, ex.crees), (1, 1))
        self.assertTrue(connu.signaux.filter(type="site", source="BODACC").exists())
        self.assertTrue(Compte.objects.get(siren="111111118").signaux.filter(type="site").exists())

    def test_georisques_marque_icpe(self):
        connu = Compte.objects.create(nom="Usine connue", siren="555555556", segment="industrie", effectif=150)
        r = RechercheAuto.objects.get(source="georisques")
        r.departements = "60"
        r.save()
        with mock.patch("prospection.services.recherche.get_json", return_value={"data": [{"siret": "55555555600012", "raisonSociale": "USINE", "regime": "Autorisation"}]}):
            ex = recherche.executer(r)
        connu.refresh_from_db()
        self.assertTrue(connu.icpe)
        self.assertEqual(ex.signaux, 1)

    def test_source_en_panne_et_saison(self):
        with mock.patch("prospection.services.recherche.get_json", side_effect=RuntimeError("503")):
            ex = recherche.executer(self.r)
        self.assertIn("503", ex.erreur)
        h = RechercheAuto.objects.get(nom__startswith="Hôtellerie")
        self.assertTrue(h.active_ce_mois(3))
        self.assertFalse(h.active_ce_mois(11))

    def test_ecrans(self):
        u = User.objects.create_user("julie", password="x", is_staff=True, is_superuser=True)
        self.client.force_login(u)
        self.assertContains(self.client.get("/prospection/recherche-automatique/"), "Logistique et entreposage")
        self.assertContains(self.client.get(f"/prospection/recherche-automatique/?id={self.r.pk}"), "Modifier")
        with mock.patch("prospection.views_recherche._lancer_en_arriere_plan") as lancer:
            self.client.post("/prospection/recherche-automatique/", {"action": "lancer", "id": self.r.pk})
            lancer.assert_called_once()
        self.client.post("/prospection/recherche-automatique/", {"action": "enregistrer", "nom": "Test 95", "source": "sirene", "codes_naf": "52.10B",
                                                                 "departements": "95", "effectif_min": "20", "etablissements_min": "1", "palier_min": "B", "max_par_nuit": "5"})
        self.assertTrue(RechercheAuto.objects.filter(nom="Test 95", effectif_min=20).exists())
        ExecutionRecherche.objects.create(recherche=self.r, examines=40, crees=3)
        self.assertContains(self.client.get("/prospection/"), "Voir les prospects trouvés")
        self.assertEqual(self.client.get("/prospection/prospects/?vue=auto").status_code, 200)


# ---------------------------------------------------------------------------- France Travail

from .services import francetravail as ft  # noqa: E402


class FauxHttpFT:
    def __init__(self, reponses):
        self.reponses, self.appels = list(reponses), []

    def post(self, url, **kw):
        self.appels.append(("POST", url, kw))
        return SimpleNamespace(status_code=200, json=lambda: {"access_token": "jeton-ft", "expires_in": 1499})

    def get(self, url, **kw):
        self.appels.append(("GET", url, kw))
        code, data = self.reponses.pop(0)
        return SimpleNamespace(status_code=code, json=lambda: data, text=str(data))


def offre(id_, nom, intitule="Responsable QSE", cp="95100", naf=""):
    return {"id": id_, "intitule": intitule, "dateCreation": "2026-11-20T10:00:00.000Z", "codeNAF": naf,
            "entreprise": {"nom": nom}, "lieuTravail": {"libelle": "95 - Argenteuil", "codePostal": cp}}


@mock.patch.dict("os.environ", {"FRANCETRAVAIL_CLIENT_ID": "id", "FRANCETRAVAIL_CLIENT_SECRET": "secret"})
@mock.patch("prospection.services.recherche.time.sleep", lambda s: None)
class FranceTravail(TestCase):
    def setUp(self):
        ft._cache.clear()
        self.qse = RechercheAuto.objects.get(nom__startswith="Recrutements QSE")
        self.volume = RechercheAuto.objects.get(nom__startswith="Recrutements en nombre")

    def test_client_pages_et_jeton(self):
        h = FauxHttpFT([(206, {"resultats": [offre(str(i), "A") for i in range(150)]}), (206, {"resultats": [offre("x", "B")]})])
        res = ft.offres({"motsCles": "QSE"}, client=h)
        self.assertEqual(len(res), 151)
        self.assertEqual(h.appels[0][2]["data"]["scope"], "api_offresdemploiv2 o2dsoffre")
        self.assertEqual([a[2]["params"]["range"] for a in h.appels if a[0] == "GET"], ["0-149", "150-299"])
        self.assertEqual(ft.offres({}, client=FauxHttpFT([(204, {})])), [])
        with self.assertRaises(ft.FranceTravailIndisponible):
            ft.offres({}, client=FauxHttpFT([(401, {})]))

    def test_qse_cree_prospect_et_signal(self):
        connu = Compte.objects.create(nom="Usine Connue", segment="industrie", effectif=200)
        offres = [offre("1", "Entrepots du Nord"), offre("2", "Usine Connue", intitule="Animateur HSE"), offre("3", "ADECCO Argenteuil"), offre("4", "")]
        with mock.patch("prospection.services.francetravail.offres", return_value=offres), \
             mock.patch("prospection.services.recherche._sirene_par_nom", return_value=entreprise("111111118", "ENTREPOTS DU NORD")):
            ex = recherche.executer(self.qse)
        self.assertEqual((ex.crees, ex.signaux, ex.erreur), (1, 1, ""))
        c = Compte.objects.get(siren="111111118")
        s = c.signaux.get()
        self.assertEqual((s.type, s.source), ("qse", "France Travail"))
        self.assertIn("Responsable QSE", s.texte)
        self.assertTrue(connu.signaux.filter(type="qse").exists())
        self.assertFalse(Compte.objects.filter(nom__icontains="adecco").exists())

    def test_recrutement_en_nombre(self):
        offres = [offre(str(i), "Logistique Volume", intitule="Préparateur de commandes") for i in range(12)] + [offre("x", "Petite Boite")]
        with mock.patch("prospection.services.francetravail.offres", return_value=offres) as f, \
             mock.patch("prospection.services.recherche._sirene_par_nom", return_value=entreprise("111111118", "LOGISTIQUE VOLUME")):
            ex = recherche.executer(self.volume)
        self.assertIn("secteurActivite", f.call_args_list[0].args[0])
        self.assertEqual(ex.crees, 1)
        self.assertIn("12 offres", Compte.objects.get(siren="111111118").signaux.get(type="recrut").texte)

    def test_ignore_sans_identifiants(self):
        with mock.patch.dict("os.environ", {"FRANCETRAVAIL_CLIENT_ID": "", "FRANCETRAVAIL_CLIENT_SECRET": ""}):
            self.assertFalse(recherche.disponible(self.qse))
            with mock.patch("prospection.services.recherche.SOURCES", {k: (lambda r, ex: None) for k in recherche.SOURCES}):
                sources = {e.recherche.source for e in recherche.executer_tout(forcer=True)}
            self.assertNotIn("francetravail", sources)
            u = User.objects.create_user("julie", password="x", is_staff=True)
            self.client.force_login(u)
            self.assertContains(self.client.get("/prospection/recherche-automatique/"), "identifiants à renseigner")
