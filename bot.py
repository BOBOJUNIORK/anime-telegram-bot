import os
import re
import math
import logging
import html
import requests
import random
import asyncio
from datetime import datetime
from urllib.parse import quote, urlencode
import json

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from deep_translator import GoogleTranslator

# ──────────────────────────
# Logging
# ──────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ──────────────────────────
# Token via variable d'environnement
# ──────────────────────────
TOKEN = os.getenv("TOKEN")

# ──────────────────────────
# Configuration
# ──────────────────────────
STREAMING_SITES = [
    {
        "name": "VoirAnime",
        "base_url": "https://voiranime.com",
        "search_url": "https://voiranime.com/?s={query}",
        "anime_url": "https://voiranime.com/anime/{slug}"
    },
    {
        "name": "Anime-Sama",
        "base_url": "https://www.anime-sama.fr",
        "search_url": "https://www.anime-sama.fr/search/?q={query}",
        "anime_url": "https://www.anime-sama.fr/anime/{slug}"
    },
    {
        "name": "French-Anime",
        "base_url": "https://french-anime.com",
        "search_url": "https://french-anime.com/search?q={query}",
        "anime_url": "https://french-anime.com/anime/{slug}"
    },
    {
        "name": "Franime",
        "base_url": "https://franime.fr",
        "search_url": "https://franime.fr/?s={query}",
        "anime_url": "https://franime.fr/anime/{slug}"
    },
    {
        "name": "Anime-Ultime",
        "base_url": "https://www.anime-ultime.net",
        "search_url": "https://www.anime-ultime.net/search-0-0-{query}.html",
        "anime_url": "https://www.anime-ultime.net/anime-{id}-0/infos.html"
    }
]

# Configuration Nautiljon
NAUTILJON_BASE_URL = "https://www.nautiljon.com"
NAUTILJON_SEARCH_URL = f"{NAUTILJON_BASE_URL}/recherche/"

# Cache pour les recherches Nautiljon
nautiljon_cache = {}

# ──────────────────────────
# Utilitaires de texte
# ──────────────────────────
def decode_html_entities(text: str) -> str:
    """Décoder &amp;, &#x27;, etc."""
    if not text:
        return ""
    return html.unescape(text)

def escape_html(text: str) -> str:
    """Échapper pour parse_mode=HTML ( &, <, >, " )"""
    if text is None:
        return ""
    return html.escape(text, quote=True)

def truncate(s: str, limit: int) -> str:
    s = s or ""
    return (s[: limit - 3] + "...") if len(s) > limit else s

def create_slug(title: str) -> str:
    """Crée un slug à partir d'un titre d'anime"""
    # Convertir en minuscules
    slug = title.lower()
    # Remplacer les espaces par des tirets
    slug = re.sub(r'\s+', '-', slug)
    # Supprimer les caractères non alphanumériques (sauf les tirets)
    slug = re.sub(r'[^a-z0-9\-]', '', slug)
    # Supprimer les tirets multiples
    slug = re.sub(r'\-+', '-', slug)
    # Supprimer les tirets en début et fin
    slug = slug.strip('-')
    return slug

# ──────────────────────────
# Appels API Jikan
# ──────────────────────────
def search_anime(query, limit=10):
    url = f"https://api.jikan.moe/v4/anime?q={query}&limit={limit}"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            return data.get("data") or None
        logger.error(f"Erreur API Jikan: {r.status_code}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Erreur de connexion: {e}")
    return None

def get_anime_by_id(anime_id):
    url = f"https://api.jikan.moe/v4/anime/{anime_id}"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            return r.json().get("data")
    except requests.exceptions.RequestException as e:
        logger.error(f"Erreur de connexion: {e}")
    return None

def get_anime_by_season(year, season):
    url = f"https://api.jikan.moe/v4/seasons/{year}/{season}"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            return (r.json().get("data") or [])[:20]
        logger.error(f"Erreur API Jikan: {r.status_code}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Erreur de connexion: {e}")
    return None

def search_character(query, limit=10):
    url = f"https://api.jikan.moe/v4/characters?q={query}&limit={limit}"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            return data.get("data") or None
        logger.error(f"Erreur API Jikan: {r.status_code}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Erreur de connexion: {e}")
    return None

def get_character_by_id(character_id):
    """Récupère les détails complets d'un personnage par son ID"""
    url = f"https://api.jikan.moe/v4/characters/{character_id}/full"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            return r.json().get("data")
        logger.error(f"Erreur API Jikan (character): {r.status_code}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Erreur de connexion (character): {e}")
    return None

def get_anime_characters(anime_id):
    """Récupère tous les personnages d'un anime"""
    url = f"https://api.jikan.moe/v4/anime/{anime_id}/characters"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            return data.get("data") or []
        logger.error(f"Erreur API Jikan (anime characters): {r.status_code}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Erreur de connexion (anime characters): {e}")
    return []

def get_anime_recommendations(genres, exclude_id, limit=5):
    genre_ids = [str(g["mal_id"]) for g in genres[:2]]
    genre_query = ",".join(genre_ids)
    url = f"https://api.jikan.moe/v4/anime?genres={genre_query}&limit={limit + 1}"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json().get("data") or []
            recs = [a for a in data if a.get("mal_id") != exclude_id]
            return recs[:limit]
    except requests.exceptions.RequestException as e:
        logger.error(f"Erreur de connexion pour les recommandations: {e}")
    return None

def get_top_anime(filter_type="all", page=1):
    url = f"https://api.jikan.moe/v4/top/anime?filter={filter_type}&page={page}"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            return data.get("data") or [], data.get("pagination", {}).get("last_visible_page", 1)
        logger.error(f"Erreur API Jikan (top): {r.status_code}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Erreur de connexion (top): {e}")
    return [], 1

def get_random_anime():
    url = "https://api.jikan.moe/v4/random/anime"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            return r.json().get("data")
        logger.error(f"Erreur API Jikan (random): {r.status_code}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Erreur de connexion (random): {e}")
    return None

def get_schedule(day=None):
    if day:
        url = f"https://api.jikan.moe/v4/schedules?filter={day}"
    else:
        url = "https://api.jikan.moe/v4/schedules"
    
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            return r.json().get("data") or []
        logger.error(f"Erreur API Jikan (schedule): {r.status_code}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Erreur de connexion (schedule): {e}")
    return []

# ──────────────────────────
# Intégration Nautiljon
# ──────────────────────────
def search_nautiljon(query, search_type="anime"):
    """Recherche sur Nautiljon et retourne les résultats"""
    if query in nautiljon_cache:
        return nautiljon_cache[query]
    
    params = {
        'mot': query,
        'type': search_type
    }
    
    try:
        url = f"{NAUTILJON_SEARCH_URL}?{urlencode(params)}"
        response = requests.get(url, timeout=10, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
        if response.status_code == 200:
            # Extraction basique des résultats (simplifié)
            results = []
            pattern = r'<a href="(/[\w/-]+)" title="([^"]+)">'
            matches = re.findall(pattern, response.text)
            
            for href, title in matches[:5]:  # Limiter à 5 résultats
                if "/mangas/" in href or "/anime/" in href or "/personnages/" in href:
                    results.append({
                        'title': decode_html_entities(title),
                        'url': f"{NAUTILJON_BASE_URL}{href}"
                    })
            
            nautiljon_cache[query] = results
            return results
    except Exception as e:
        logger.error(f"Erreur recherche Nautiljon: {e}")
    
    return []

def get_nautiljon_character_info(character_name):
    """Récupère les informations détaillées d'un personnage sur Nautiljon"""
    results = search_nautiljon(character_name, "personnages")
    if results:
        # Prendre le premier résultat
        character_url = results[0]['url']
        
        try:
            response = requests.get(character_url, timeout=10, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            
            if response.status_code == 200:
                # Extraction des informations de base (simplifié)
                html_content = response.text
                
                # Extraction de la description
                description_match = re.search(r'<div class="description[^>]*>(.*?)</div>', html_content, re.DOTALL)
                description = description_match.group(1).strip() if description_match else "Aucune description disponible"
                
                # Nettoyage du HTML
                description = re.sub(r'<[^>]+>', '', description)
                description = re.sub(r'\s+', ' ', description).strip()
                
                return {
                    'name': results[0]['title'],
                    'url': character_url,
                    'description': description[:1000] + "..." if len(description) > 1000 else description
                }
        except Exception as e:
            logger.error(f"Erreur chargement personnage Nautiljon: {e}")
    
    return None

# ──────────────────────────
# Vérification des liens de streaming
# ──────────────────────────
async def check_streaming_availability(anime_title):
    """Vérifie la disponibilité sur les sites de streaming"""
    results = {}
    slug = create_slug(anime_title)
    
    for site in STREAMING_SITES:
        try:
            # Essayer d'abord avec l'URL directe
            if "anime_url" in site:
                if "{slug}" in site["anime_url"]:
                    test_url = site["anime_url"].format(slug=slug)
                else:
                    # Pour Anime-Ultime qui utilise un ID, on utilise la recherche
                    test_url = site["search_url"].format(query=quote(anime_title))
                
                # Faire une requête HEAD pour vérifier si la page existe
                response = requests.head(test_url, timeout=5, allow_redirects=True)
                
                if response.status_code == 200:
                    results[site["name"]] = test_url
                    continue
            
            # Fallback sur la recherche
            search_url = site["search_url"].format(query=quote(anime_title))
            results[site["name"]] = search_url
                
        except requests.exceptions.RequestException:
            # En cas d'erreur, utiliser l'URL de recherche
            search_url = site["search_url"].format(query=quote(anime_title))
            results[site["name"]] = search_url
    
    return results

# ──────────────────────────
# Formatage (HTML)
# ──────────────────────────
def format_anime_basic_info(anime):
    titre = escape_html(decode_html_entities(anime.get("title", "Titre inconnu")))
    titre_jp = escape_html(decode_html_entities(anime.get("title_japanese", ""))) or "N/A"
    score = escape_html(str(anime.get("score", "N/A")))
    episodes = escape_html(str(anime.get("episodes", "Inconnu")))
    status = escape_html(decode_html_entities(anime.get("status", "Inconnu")))
    year = escape_html(str(anime.get("year", "N/A")))

    caption = (
        f"🎌 <b>{titre}</b>{f' ({titre_jp})' if titre_jp != 'N/A' else ''}\n\n"
        f"⭐ <b>Note</b> : {score}/10\n"
        f"📺 <b>Épisodes</b> : {episodes}\n"
        f"📊 <b>Statut</b> : {status}\n"
        f"📅 <b>Année</b> : {year}\n\n"
        f"👇 <b>Utilisez les boutons pour plus d'infos</b>"
    )
    # Limite caption Telegram: 1024
    return truncate(caption, 1024)

def format_synopsis(anime):
    titre = escape_html(decode_html_entities(anime.get("title", "Titre inconnu")))
    synopsis = decode_html_entities(anime.get("synopsis", "Pas de synopsis disponible"))
    try:
        if synopsis and synopsis != "Pas de synopsis disponible":
            synopsis_short = truncate(synopsis, 800)
            synopsis_fr = GoogleTranslator(source="auto", target="fr").translate(synopsis_short)
        else:
            synopsis_fr = synopsis
    except Exception as e:
        logger.error(f"Erreur de traduction: {e}")
        synopsis_fr = synopsis

    synopsis_fr = escape_html(synopsis_fr)
    return f"📝 <b>Synopsis de {titre}</b> :\n\n{synopsis_fr}"

def format_details(anime):
    titre = escape_html(decode_html_entities(anime.get("title", "Titre inconnu")))
    rating = escape_html(decode_html_entities(anime.get("rating", "N/A")))
    duration = escape_html(anime.get("duration", "N/A"))
    source = escape_html(decode_html_entities(anime.get("source", "N/A")))
    genres = ", ".join(escape_html(decode_html_entities(g["name"])) for g in anime.get("genres", []))

    return (
        f"🔍 <b>Détails de {titre}</b> :\n\n"
        f"🎭 <b>Genres</b> : {genres or 'N/A'}\n"
        f"⏱️ <b>Durée par épisode</b> : {duration}\n"
        f"📚 <b>Source</b> : {source}\n"
        f"🔞 <b>Classification</b> : {rating}"
    )

def format_studio_info(anime):
    titre = escape_html(decode_html_entities(anime.get("title", "Titre inconnu")))
    studios = [escape_html(decode_html_entities(s["name"])) for s in anime.get("studios", [])]
    producers = [escape_html(decode_html_entities(p["name"])) for p in anime.get("producers", [])]

    studio_text = ", ".join(studios) if studios else "Inconnu"
    producer_text = ", ".join(producers[:3]) if producers else "Inconnu"

    return (
        f"🏢 <b>Infos production de {titre}</b> :\n\n"
        f"🎬 <b>Studio(s)</b> : {studio_text}\n"
        f"👔 <b>Producteur(s)</b> : {producer_text}"
    )

def format_character_info(character, nautiljon_data=None):
    """Formatage amélioré des informations sur les personnages"""
    name = escape_html(decode_html_entities(character.get("name", "Nom inconnu")))
    name_kanji = escape_html(decode_html_entities(character.get("name_kanji", "")))
    about = decode_html_entities(character.get("about", "Pas d'informations disponibles"))
    
    # Récupérer les informations supplémentaires si disponibles
    nicknames = character.get("nicknames", [])
    favorites = character.get("favorites", 0)
    animeography = character.get("animeography", [])
    voice_actors = character.get("voices", []) if isinstance(character.get("voices"), list) else []
    
    # Utiliser les données Nautiljon si disponibles
    if nautiljon_data:
        about = nautiljon_data.get('description', about)
    
    # Traduire la description
    try:
        if about and about != "Pas d'informations disponibles":
            # Utiliser plus de texte pour une meilleure description
            about_to_translate = about[:2000]  # Augmenter la limite
            about_fr = GoogleTranslator(source="auto", target="fr").translate(about_to_translate)
        else:
            about_fr = about
    except Exception as e:
        logger.error(f"Erreur de traduction personnage: {e}")
        about_fr = about
    
    about_fr = escape_html(about_fr)
    
    # Construction du texte
    text = f"👤 <b>{name}</b>"
    if name_kanji:
        text += f" ({name_kanji})"
    
    if nicknames:
        text += f"\n🎭 <b>Surnoms</b>: {', '.join([escape_html(n) for n in nicknames])}"
    
    text += f"\n❤️ <b>Favoris</b>: {favorites}"
    
    if about_fr:
        text += f"\n\n📝 <b>Description</b>:\n{about_fr}"
    
    # Ajouter les anime principaux
    if animeography:
        main_anime = [a for a in animeography if a.get("role") == "Main"]
        if main_anime:
            text += f"\n\n📺 <b>Anime principal</b>: {escape_html(main_anime[0].get('name', 'Inconnu'))}"
    
    # Ajouter les doubleurs (seiyuu)
    if voice_actors:
        japanese_va = [va for va in voice_actors if va.get('language') == 'Japanese']
        if japanese_va:
            va_name = japanese_va[0].get('person', {}).get('name', 'Inconnu')
            text += f"\n🎙️ <b>Seiyuu</b>: {escape_html(va_name)}"
    
    # Ajouter le lien Nautiljon si disponible
    if nautiljon_data:
        text += f"\n\n🔗 <a href='{nautiljon_data['url']}'>Voir plus sur Nautiljon</a>"
    
    return text

def format_anime_characters_list(anime_title, characters):
    """Formate la liste des personnages d'un anime"""
    title = escape_html(decode_html_entities(anime_title))
    text = f"👥 <b>Personnages de {title}</b>\n\n"
    
    # Séparer les personnages principaux et secondaires
    main_characters = [c for c in characters if c.get("role") == "Main"]
    supporting_characters = [c for c in characters if c.get("role") == "Supporting"]
    
    if main_characters:
        text += "🎯 <b>Personnages Principaux</b>:\n"
        for i, character in enumerate(main_characters[:10], 1):  # Limiter à 10
            name = escape_html(decode_html_entities(character.get("character", {}).get("name", "Inconnu")))
            text += f"{i}. {name}\n"
    
    if supporting_characters:
        text += "\n👥 <b>Personnages Secondaires</b>:\n"
        for i, character in enumerate(supporting_characters[:10], 1):  # Limiter à 10
            name = escape_html(decode_html_entities(character.get("character", {}).get("name", "Inconnu")))
            text += f"{i}. {name}\n"
    
    if len(main_characters) > 10 or len(supporting_characters) > 10:
        text += f"\n... et {max(0, len(main_characters) - 10) + max(0, len(supporting_characters) - 10)} autres personnages"
    
    return text

def format_streaming_links(anime, streaming_links):
    """Formate les liens de streaming pour l'anime"""
    titre = escape_html(decode_html_entities(anime.get("title", "Titre inconnu")))
    
    # Créer le texte avec les liens
    text = f"📺 <b>Regarder {titre}</b>:\n\n"
    text += "Voici où vous pourriez trouver cet anime:\n\n"
    
    for site_name, url in streaming_links.items():
        text += f"• <a href='{escape_html(url)}'>{escape_html(site_name)}</a>\n"
    
    text += "\n🔍 <i>Note: Ces liens mènent directement aux animes quand disponibles, sinon à des pages de recherche.</i>"
    
    return text

def format_top_anime_list(anime_list, filter_type, page, total_pages):
    """Formate la liste des top animes"""
    filter_names = {
        "all": "Tous les temps",
        "airing": "En cours de diffusion",
        "upcoming": "À venir",
        "tv": "Séries TV",
        "movie": "Films",
        "ova": "OVA",
        "special": "Spéciaux",
        "bypopularity": "Populaires",
        "favorite": "Favoris"
    }
    
    text = f"🏆 <b>Top Anime - {filter_names.get(filter_type, filter_type)}</b>\n\n"
    
    for i, anime in enumerate(anime_list, 1):
        title = escape_html(decode_html_entities(anime.get("title", "Titre inconnu")))
        score = escape_html(str(anime.get("score", "N/A")))
        text += f"{i}. {title} ⭐ {score}\n"
    
    text += f"\n📄 Page {page}/{total_pages}"
    return text

def format_schedule(schedule_list, day=None):
    """Formate le planning des sorties"""
    day_names = {
        "monday": "Lundi",
        "tuesday": "Mardi",
        "wednesday": "Mercredi",
        "thursday": "Jeudi",
        "friday": "Vendredi",
        "saturday": "Samedi",
        "sunday": "Dimanche",
        "other": "Autre",
        "unknown": "Inconnu"
    }
    
    if day:
        title = f"📅 <b>Sorties du {day_names.get(day, day)}</b>\n\n"
    else:
        title = "📅 <b>Sorties de la semaine</b>\n\n"
    
    if not schedule_list:
        return title + "Aucune sortie prévue pour cette période."
    
    text = title
    for anime in schedule_list[:10]:  # Limiter à 10 résultats
        title = escape_html(decode_html_entities(anime.get("title", "Titre inconnu")))
        score = escape_html(str(anime.get("score", "N/A")))
        text += f"• {title}"
        if score != "N/A":
            text += f" ⭐ {score}"
        text += "\n"
    
    if len(schedule_list) > 10:
        text += f"\n... et {len(schedule_list) - 10} autres"
    
    return text

# ──────────────────────────
# Claviers inline 
# ──────────────────────────
def create_anime_navigation_keyboard(anime_id):
    keyboard = [
        [
            InlineKeyboardButton("📝 Synopsis", callback_data=f"synopsis_{anime_id}"),
            InlineKeyboardButton("🔍 Détails", callback_data=f"details_{anime_id}"),
        ],
        [
            InlineKeyboardButton("🏢 Studio", callback_data=f"studio_{anime_id}"),
            InlineKeyboardButton("🎬 Trailer", callback_data=f"trailer_{anime_id}"),
        ],
        [
            InlineKeyboardButton("👥 Personnages", callback_data=f"anime_chars_{anime_id}"),
            InlineKeyboardButton("🎯 Similaires", callback_data=f"similar_{anime_id}"),
        ],
        [
            InlineKeyboardButton("📺 Streaming", callback_data=f"streaming_{anime_id}"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)

def create_characters_list_keyboard(characters, anime_id, page=0, items_per_page=10):
    """Crée un clavier pour la liste des personnages d'un anime"""
    keyboard = []
    start_idx = page * items_per_page
    end_idx = min(start_idx + items_per_page, len(characters))
    
    for i in range(start_idx, end_idx):
        character = characters[i]
        char_data = character.get("character", {})
        name = decode_html_entities(char_data.get("name", "Sans nom"))
        character_id = char_data.get("mal_id")
        
        if len(name) > 30:
            name = name[:27] + "..."
        
        role = character.get("role", "")
        if role == "Main":
            name = "🎯 " + name
        elif role == "Supporting":
            name = "👥 " + name
        
        keyboard.append([InlineKeyboardButton(name, callback_data=f"character_{character_id}")])
    
    # Ajouter la pagination si nécessaire
    total_pages = math.ceil(len(characters) / items_per_page)
    if total_pages > 1:
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️", callback_data=f"chars_page_{anime_id}_{page-1}"))
        nav_buttons.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="noop"))
        if page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton("➡️", callback_data=f"chars_page_{anime_id}_{page+1}"))
        keyboard.append(nav_buttons)
    
    # Ajouter le bouton retour
    keyboard.append([InlineKeyboardButton("🔙 Retour à l'anime", callback_data=f"anime_{anime_id}")])
    
    return InlineKeyboardMarkup(keyboard)

def create_search_pagination_keyboard(results, current_page=0, query="", search_type="anime"):
    keyboard = []
    items_per_page = 5
    total_pages = max(1, math.ceil(len(results) / items_per_page))

    start_idx = current_page * items_per_page
    end_idx = min(start_idx + items_per_page, len(results))

    for i in range(start_idx, end_idx):
        item = results[i]
        if search_type == "anime":
            title = decode_html_entities(item.get("title", "Sans titre"))
            item_id = item.get("mal_id")
            callback_prefix = "anime"
        else:
            title = decode_html_entities(item.get("name", "Sans nom"))
            item_id = item.get("mal_id")
            callback_prefix = "character"
        if len(title) > 35:
            title = title[:32] + "..."
        # (Les labels de boutons n'ont pas besoin d'échappement HTML)
        keyboard.append([InlineKeyboardButton(title, callback_data=f"{callback_prefix}_{item_id}")])

    if total_pages > 1:
        nav_row = []
        if current_page > 0:
            nav_row.append(InlineKeyboardButton("⬅️", callback_data=f"page_{search_type}_{query}_{current_page-1}"))
        nav_row.append(InlineKeyboardButton(f"{current_page + 1}/{total_pages}", callback_data="noop"))
        if current_page < total_pages - 1:
            nav_row.append(InlineKeyboardButton("➡️", callback_data=f"page_{search_type}_{query}_{current_page+1}"))
        keyboard.append(nav_row)

    return InlineKeyboardMarkup(keyboard)

def create_top_anime_keyboard(current_filter="all", current_page=1, total_pages=1):
    """Crée un clavier pour la navigation des top animes"""
    filter_buttons = [
        [
            InlineKeyboardButton("🎯 Tous", callback_data="top_all_1"),
            InlineKeyboardButton("📡 En cours", callback_data="top_airing_1"),
            InlineKeyboardButton("🔮 À venir", callback_data="top_upcoming_1"),
        ],
        [
            InlineKeyboardButton("📺 Séries", callback_data="top_tv_1"),
            InlineKeyboardButton("🎬 Films", callback_data="top_movie_1"),
            InlineKeyboardButton("💎 OVA", callback_data="top_ova_1"),
        ],
        [
            InlineKeyboardButton("⭐ Populaires", callback_data="top_bypopularity_1"),
            InlineKeyboardButton("❤️ Favoris", callback_data="top_favorite_1"),
        ]
    ]
    
    # Navigation des pages
    navigation_buttons = []
    if current_page > 1:
        navigation_buttons.append(InlineKeyboardButton("⬅️", callback_data=f"top_{current_filter}_{current_page-1}"))
    
    navigation_buttons.append(InlineKeyboardButton(f"{current_page}/{total_pages}", callback_data="noop"))
    
    if current_page < total_pages:
        navigation_buttons.append(InlineKeyboardButton("➡️", callback_data=f"top_{current_filter}_{current_page+1}"))
    
    if navigation_buttons:
        filter_buttons.append(navigation_buttons)
    
    return InlineKeyboardMarkup(filter_buttons)

def create_schedule_keyboard():
    """Crée un clavier pour la navigation du planning"""
    days = [
        [
            InlineKeyboardButton("📅 Aujourd'hui", callback_data="schedule_today"),
            InlineKeyboardButton("📅 Semaine", callback_data="schedule_week"),
        ],
        [
            InlineKeyboardButton("🗓️ Lundi", callback_data="schedule_monday"),
            InlineKeyboardButton("🗓️ Mardi", callback_data="schedule_tuesday"),
            InlineKeyboardButton("🗓️ Mercredi", callback_data="schedule_wednesday"),
        ],
        [
            InlineKeyboardButton("🗓️ Jeudi", callback_data="schedule_thursday"),
            InlineKeyboardButton("🗓️ Vendredi", callback_data="schedule_friday"),
            InlineKeyboardButton("🗓️ Samedi", callback_data="schedule_saturday"),
        ],
        [
            InlineKeyboardButton("🗓️ Dimanche", callback_data="schedule_sunday"),
        ]
    ]
    return InlineKeyboardMarkup(days)

# ──────────────────────────
# Claviers inline pour les sous-pages
# ──────────────────────────
def create_back_button_keyboard(anime_id):
    """Crée un clavier avec uniquement le bouton Retour"""
    keyboard = [
        [InlineKeyboardButton("🔙 Retour à l'anime", callback_data=f"anime_{anime_id}")]
    ]
    return InlineKeyboardMarkup(keyboard)

def create_similar_animes_keyboard(similar_animes, original_anime_id):
    """Crée un clavier pour les animes similaires avec bouton retour"""
    keyboard = []
    for anime in similar_animes:
        title = decode_html_entities(anime.get("title", "Sans titre"))
        if len(title) > 35:
            title = title[:32] + "..."
        keyboard.append([InlineKeyboardButton(title, callback_data=f"anime_{anime['mal_id']}")])
    
    # Ajouter le bouton retour
    keyboard.append([InlineKeyboardButton("🔙 Retour", callback_data=f"anime_{original_anime_id}")])
    
    return InlineKeyboardMarkup(keyboard)

# ──────────────────────────
# Commandes
# ──────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("🔍 Rechercher un anime", switch_inline_query_current_chat="")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    welcome_text = (
        "👋 Bonjour ! Je suis votre assistant pour découvrir des animes.\n\n"
        "✨ <b>Fonctionnalités :</b>\n"
        "• 🔍 Recherche d'animes avec navigation interactive\n"
        "• 📝 Synopsis détaillés et traduits\n"
        "• 🎬 Liens vers les trailers officiels\n"
        "• 🎯 Recommandations d'animes similaires\n"
        "• 📅 Recherche par saison\n"
        "• 👤 Recherche de personnages\n"
        "• 🏆 Top animes\n"
        "• 🎲 Anime aléatoire\n"
        "• 📅 Planning des sorties\n"
        "• 👥 Fonctionne dans les groupes et en privé\n\n"
        "💡 <b>Commandes disponibles :</b>\n"
        "• Tapez le nom d'un anime pour le rechercher\n"
        "• <code>/saison &lt;année&gt; &lt;saison&gt;</code> (ex : <code>/saison 2023 fall</code>)\n"
        "• <code>/personnage &lt;nom&gt;</code> (ex : <code>/personnage Naruto</code>)\n"
        "• <code>/top</code> - Liste des meilleurs animes\n"
        "• <code>/random</code> - Anime aléatoire\n"
        "• <code>/planning</code> - Planning des sorties\n"
        "• <code>/anime &lt;nom&gt;</code> ou <code>/recherche &lt;nom&gt;</code>"
    )
    await update.message.reply_text(welcome_text, parse_mode="HTML", reply_markup=reply_markup)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "🤖 <b>Aide - Bot Anime</b>\n\n"
        "🔍 <b>Recherche d'animes :</b>\n"
        "• Tapez le nom d'un anime\n"
        "• <code>/recherche &lt;nom&gt;</code> ou <code>/anime &lt;nom&gt;</code>\n\n"
        "📅 <b>Recherche par saison :</b>\n"
        "• <code>/saison &lt;année&gt; &lt;saison&gt;</code> (spring, summer, fall, winter)\n"
        "• ex : <code>/saison 2023 fall</code>\n\n"
        "👤 <b>Recherche de personnages :</b>\n"
        "• <code>/personnage &lt;nom&gt;</code>\n"
        "• ex : <code>/personnage Naruto</code>\n\n"
        "🏆 <b>Top animes :</b>\n"
        "• <code>/top</code> - Liste des meilleurs animes\n\n"
        "🎲 <b>Anime aléatoire :</b>\n"
        "• <code>/random</code> - Découvrir un anime au hasard\n\n"
        "📅 <b>Planning des sorties :</b>\n"
        "• <code>/planning</code> - Voir les sorties de la semaine\n\n"
        "🎯 <b>Navigation interactive :</b>\n"
        "• Boutons : Synopsis, Détails, Studio, Trailer, Personnages, Similaires, Streaming\n\n"
        "👥 <b>Groupes :</b>\n"
        "• Mentionne-moi puis écris le nom de l'anime"
    )
    await update.message.reply_text(help_text, parse_mode="HTML")

# ──────────────────────────
# Nouvelles commandes
# ──────────────────────────
async def season_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text(
            "❌ Format incorrect. Utilisez : <code>/saison &lt;année&gt; &lt;saison&gt;</code>\n"
            "Saisons : <code>spring</code>, <code>summer</code>, <code>fall</code>, <code>winter</code>\n"
            "Exemple : <code>/saison 2023 fall</code>",
            parse_mode="HTML",
        )
        return

    year = context.args[0]
    season = context.args[1].lower()
    valid_seasons = ["spring", "summer", "fall", "winter"]
    if season not in valid_seasons:
        await update.message.reply_text(
            f"❌ Saison invalide. Utilisez : {', '.join(valid_seasons)}", parse_mode="HTML"
        )
        return

    await update.message.reply_chat_action(action="typing")
    results = get_anime_by_season(year, season)
    if not results:
        await update.message.reply_text(f"❌ Aucun anime trouvé pour {season} {year}.", parse_mode="HTML")
        return

    context.user_data[f"season_results_{year}_{season}"] = results

    season_names = {"spring": "Printemps", "summer": "Été", "fall": "Automne", "winter": "Hiver"}
    keyboard = create_search_pagination_keyboard(results, 0, f"{year}_{season}", "anime")

    await update.message.reply_text(
        f"📅 <b>Animes de {season_names[season]} {escape_html(str(year))}</b>\n"
        f"Trouvé {len(results)} anime(s). Sélectionnez celui qui vous intéresse :",
        parse_mode="HTML",
        reply_markup=keyboard,
    )

async def character_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "❌ Veuillez spécifier un nom de personnage. Exemple : <code>/personnage Naruto</code>",
            parse_mode="HTML",
        )
        return

    query = " ".join(context.args)
    await update.message.reply_chat_action(action="typing")
    results = search_character(query)
    if not results:
        await update.message.reply_text(f"❌ Aucun personnage trouvé pour « {escape_html(query)} ».", parse_mode="HTML")
        return

    context.user_data[f"character_results_{query}"] = results
    if len(results) == 1:
        await display_character_info(update, results[0])
    else:
        keyboard = create_search_pagination_keyboard(results, 0, query, "character")
        await update.message.reply_text(
            f"👤 Personnages trouvés pour « {escape_html(query)} » :\nSélectionnez celui qui vous intéresse :",
            parse_mode="HTML",
            reply_markup=keyboard,
        )

async def top_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche les top animes avec filtres"""
    await update.message.reply_chat_action(action="typing")
    
    # Récupérer les top animes (par défaut: tous)
    anime_list, total_pages = get_top_anime("all", 1)
    
    if not anime_list:
        await update.message.reply_text("❌ Impossible de charger les top animes.", parse_mode="HTML")
        return
    
    text = format_top_anime_list(anime_list, "all", 1, total_pages)
    keyboard = create_top_anime_keyboard("all", 1, total_pages)
    
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)

async def random_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche un anime aléatoire"""
    await update.message.reply_chat_action(action="typing")
    
    anime = get_random_anime()
    if not anime:
        await update.message.reply_text("❌ Impossible de charger un anime aléatoire.", parse_mode="HTML")
        return
    
    await display_anime_with_navigation(update, anime)

async def planning_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche le planning des sorties"""
    await update.message.reply_chat_action(action="typing")
    
    # Déterminer le jour actuel si non spécifié
    day = context.args[0].lower() if context.args else None
    day_names = {
        "monday": "lundi", "tuesday": "mardi", "wednesday": "mercredi",
        "thursday": "jeudi", "friday": "vendredi", "saturday": "samedi",
        "sunday": "dimanche"
    }
    
    # Si "today" est demandé, déterminer le jour actuel
    if day == "today":
        today = datetime.now().strftime("%A").lower()
        day = today
    
    schedule = get_schedule(day)
    text = format_schedule(schedule, day)
    keyboard = create_schedule_keyboard()
    
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)

# ──────────────────────────
# Affichages
# ──────────────────────────
async def display_character_info(update_or_query, character):
    # Récupérer les données Nautiljon pour enrichir la description
    character_name = character.get("name", "")
    nautiljon_data = get_nautiljon_character_info(character_name)
    
    info_text = format_character_info(character, nautiljon_data)
    image_url = character["images"]["jpg"]["image_url"]

    if hasattr(update_or_query, "callback_query") and update_or_query.callback_query:
        message = update_or_query.callback_query.message
    elif hasattr(update_or_query, "message") and not hasattr(update_or_query, "callback_query"):
        message = update_or_query.message
    else:
        message = update_or_query.message

    await message.reply_photo(photo=image_url, caption=info_text, parse_mode="HTML")

async def display_anime_with_navigation(update_or_query, anime, edit_message=False):
    image_url = anime["images"]["jpg"]["large_image_url"]
    caption = format_anime_basic_info(anime)
    keyboard = create_anime_navigation_keyboard(anime["mal_id"])

    if hasattr(update_or_query, "callback_query") and update_or_query.callback_query:
        query = update_or_query.callback_query
        message = query.message
    elif hasattr(update_or_query, "message") and not hasattr(update_or_query, "callback_query"):
        message = update_or_query.message
        query = None
    else:
        query = update_or_query
        message = query.message

    try:
        if edit_message and query:
            # En cas d'édition, on renvoie un nouveau message si l'API refuse l'edit
            await query.edit_message_caption(caption=caption, parse_mode="HTML", reply_markup=keyboard)
        else:
            await message.reply_photo(photo=image_url, caption=caption, parse_mode="HTML", reply_markup=keyboard)
    except Exception as e:
        logger.error(f"Erreur lors de l'affichage de l'anime: {e}")
        await message.reply_photo(photo=image_url, caption=caption, parse_mode="HTML", reply_markup=keyboard)

# ──────────────────────────
# Recherche & messages
# ──────────────────────────
async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "❌ Veuillez spécifier un anime. Exemple : <code>/recherche One Piece</code>", parse_mode="HTML"
        )
        return
    query = " ".join(context.args)
    await perform_search(update, query, context)

async def anime_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "❌ Veuillez spécifier un anime. Exemple : <code>/anime Attack on Titan</code>", parse_mode="HTML"
        )
        return
    query = " ".join(context.args)
    await perform_search(update, query, context)

async def perform_search(update: Update, query: str, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_chat_action(action="typing")
    results = search_anime(query)
    if not results:
        await update.message.reply_text("❌ Aucun anime trouvé. Essayez avec un autre nom.", parse_mode="HTML")
        return

    context.user_data[f"search_results_{query}"] = results
    if len(results) == 1:
        await display_anime_with_navigation(update, results[0])
    else:
        keyboard = create_search_pagination_keyboard(results, 0, query, "anime")
        await update.message.reply_text(
            f"🔍 {len(results)} animes trouvés pour « {escape_html(query)} » :\nSélectionnez celui qui vous intéresse :",
            parse_mode="HTML",
            reply_markup=keyboard,
        )

# ──────────────────────────
# Boutons inline
# ──────────────────────────
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("page_"):
        parts = data.split("_")
        if len(parts) >= 4:
            search_type = parts[1]
            search_query = "_".join(parts[2:-1])
            page = int(parts[-1])

            if search_type == "anime":
                stored_key = f"search_results_{search_query}"
                if f"season_results_{search_query}" in context.user_data:
                    stored_key = f"season_results_{search_query}"
                results = context.user_data.get(stored_key, [])
                if results:
                    keyboard = create_search_pagination_keyboard(results, page, search_query, "anime")
                    await query.edit_message_reply_markup(reply_markup=keyboard)
            elif search_type == "character":
                stored_key = f"character_results_{search_query}"
                results = context.user_data.get(stored_key, [])
                if results:
                    keyboard = create_search_pagination_keyboard(results, page, search_query, "character")
                    await query.edit_message_reply_markup(reply_markup=keyboard)

    elif data.startswith("anime_"):
        anime_id = data.split("_")[1]
        anime = get_anime_by_id(anime_id)
        if anime:
            await display_anime_with_navigation(query, anime)
        else:
            await query.message.reply_text("❌ Erreur lors du chargement des détails de l'anime.", parse_mode="HTML")

    elif data.startswith("character_"):
        character_id = data.split("_")[1]
        for key, results in context.user_data.items():
            if key.startswith("character_results_"):
                character = next((c for c in results if c["mal_id"] == int(character_id)), None)
                if character:
                    await display_character_info(query, character)
                    return
        await query.message.reply_text("❌ Erreur lors du chargement des détails du personnage.", parse_mode="HTML")

    elif data.startswith("synopsis_"):
        anime_id = data.split("_")[1]
        anime = get_anime_by_id(anime_id)
        if anime:
            synopsis_text = format_synopsis(anime)
            reply_markup = create_back_button_keyboard(anime_id)
            await query.message.reply_text(synopsis_text, parse_mode="HTML", reply_markup=reply_markup)
        else:
            await query.message.reply_text("❌ Impossible de charger le synopsis.", parse_mode="HTML")

    elif data.startswith("details_"):
        anime_id = data.split("_")[1]
        anime = get_anime_by_id(anime_id)
        if anime:
            details_text = format_details(anime)
            reply_markup = create_back_button_keyboard(anime_id)
            await query.message.reply_text(details_text, parse_mode="HTML", reply_markup=reply_markup)
        else:
            await query.message.reply_text("❌ Impossible de charger les détails.", parse_mode="HTML")

    elif data.startswith("studio_"):
        anime_id = data.split("_")[1]
        anime = get_anime_by_id(anime_id)
        if anime:
            studio_text = format_studio_info(anime)
            reply_markup = create_back_button_keyboard(anime_id)
            await query.message.reply_text(studio_text, parse_mode="HTML", reply_markup=reply_markup)
        else:
            await query.message.reply_text("❌ Impossible de charger les infos studio.", parse_mode="HTML")

    elif data.startswith("trailer_"):
        anime_id = data.split("_")[1]
        anime = get_anime_by_id(anime_id)
        if anime:
            trailer_url = None
            if anime.get("trailer") and anime["trailer"].get("url"):
                trailer_url = anime["trailer"]["url"]
            if trailer_url:
                titre = escape_html(decode_html_entities(anime.get("title", "Cet anime")))
                reply_markup = create_back_button_keyboard(anime_id)
                await query.message.reply_text(
                    f"🎬 <b>Trailer de {titre}</b>:\n\n{escape_html(trailer_url)}", 
                    parse_mode="HTML", 
                    reply_markup=reply_markup
                )
            else:
                reply_markup = create_back_button_keyboard(anime_id)
                await query.message.reply_text(
                    "❌ Aucun trailer disponible pour cet anime.", 
                    parse_mode="HTML", 
                    reply_markup=reply_markup
                )
        else:
            await query.message.reply_text("❌ Impossible de charger le trailer.", parse_mode="HTML")

    elif data.startswith("similar_"):
        anime_id = int(data.split("_")[1])
        anime = get_anime_by_id(anime_id)
        if anime and anime.get("genres"):
            recs = get_anime_recommendations(anime["genres"], anime_id, 5)
            if recs:
                titre_original = escape_html(decode_html_entities(anime.get("title", "Cet anime")))
                reply_markup = create_similar_animes_keyboard(recs, anime_id)
                await query.message.reply_text(
                    f"🎯 <b>Animes similaires à {titre_original}</b>:\nBasé sur des genres proches :",
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                )
            else:
                reply_markup = create_back_button_keyboard(anime_id)
                await query.message.reply_text(
                    "❌ Aucune recommandation trouvée.", 
                    parse_mode="HTML", 
                    reply_markup=reply_markup
                )
        else:
            await query.message.reply_text("❌ Impossible de charger les recommandations.", parse_mode="HTML")

    elif data.startswith("streaming_"):
        anime_id = data.split("_")[1]
        anime = get_anime_by_id(anime_id)
        if anime:
            # Vérifier la disponibilité sur les sites de streaming
            streaming_links = await check_streaming_availability(anime.get("title", ""))
            streaming_text = format_streaming_links(anime, streaming_links)
            
            # Créer un clavier avec des boutons de liens
            keyboard = []
            for site_name, url in streaming_links.items():
                keyboard.append([InlineKeyboardButton(site_name, url=url)])
            
            # Ajouter un bouton retour
            keyboard.append([InlineKeyboardButton("🔙 Retour", callback_data=f"anime_{anime_id}")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.message.reply_text(streaming_text, parse_mode="HTML", reply_markup=reply_markup)
        else:
            await query.message.reply_text("❌ Impossible de charger les liens de streaming.", parse_mode="HTML")

    elif data.startswith("top_"):
        # Gestion des top animes
        parts = data.split("_")
        if len(parts) >= 3:
            filter_type = parts[1]
            page = int(parts[2])
            
            anime_list, total_pages = get_top_anime(filter_type, page)
            
            if anime_list:
                text = format_top_anime_list(anime_list, filter_type, page, total_pages)
                keyboard = create_top_anime_keyboard(filter_type, page, total_pages)
                await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)
            else:
                await query.answer("❌ Impossible de charger les top animes.")

    elif data.startswith("schedule_"):
        # Gestion du planning
        day = data.split("_")[1]
        
        if day == "today":
            today = datetime.now().strftime("%A").lower()
            day = today
        elif day == "week":
            day = None
        
        schedule = get_schedule(day)
        text = format_schedule(schedule, day)
        keyboard = create_schedule_keyboard()
        
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)
    
    elif data.startswith("anime_chars_"):
        # Afficher les personnages d'un anime
        anime_id = data.split("_")[2]
        anime = get_anime_by_id(anime_id)
        if anime:
            characters = get_anime_characters(anime_id)
            if characters:
                # Stocker les personnages dans le contexte pour la pagination
                context.user_data[f"anime_chars_{anime_id}"] = characters
                anime_title = anime.get("title", "Cet anime")
                list_text = format_anime_characters_list(anime_title, characters)
                keyboard = create_characters_list_keyboard(characters, anime_id, 0)
                await query.message.reply_text(list_text, parse_mode="HTML", reply_markup=keyboard)
            else:
                await query.message.reply_text("❌ Aucun personnage trouvé pour cet anime.", parse_mode="HTML")
        else:
            await query.message.reply_text("❌ Impossible de charger les personnages.", parse_mode="HTML")

    elif data.startswith("chars_page_"):
        # Pagination pour la liste des personnages
        parts = data.split("_")
        anime_id = parts[3]
        page = int(parts[4])
        
        characters = context.user_data.get(f"anime_chars_{anime_id}", [])
        if characters:
            anime = get_anime_by_id(anime_id)
            anime_title = anime.get("title", "Cet anime") if anime else "Cet anime"
            list_text = format_anime_characters_list(anime_title, characters)
            keyboard = create_characters_list_keyboard(characters, anime_id, page)
            await query.edit_message_text(list_text, parse_mode="HTML", reply_markup=keyboard)
        else:
            await query.answer("❌ Données de personnages non disponibles.")

    elif data.startswith("character_"):
        # Afficher les détails d'un personnage (version améliorée)
        character_id = data.split("_")[1]
        character = get_character_by_id(character_id)
        if character:
            # Pour le bouton retour, on essaie de trouver l'anime d'origine
            anime_id = None
            for key in context.user_data:
                if key.startswith("anime_chars_"):
                    anime_id = key.split("_")[2]
                    break
            
            if anime_id:
                reply_markup = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Retour aux personnages", callback_data=f"anime_chars_{anime_id}")]
                ])
            else:
                reply_markup = None
                
            # Récupérer les données Nautiljon pour enrichir la description
            character_name = character.get("name", "")
            nautiljon_data = get_nautiljon_character_info(character_name)
            
            info_text = format_character_info(character, nautiljon_data)
            image_url = character.get("images", {}).get("jpg", {}).get("image_url")
            
            if image_url:
                await query.message.reply_photo(
                    photo=image_url, 
                    caption=info_text, 
                    parse_mode="HTML", 
                    reply_markup=reply_markup
                )
            else:
                await query.message.reply_text(info_text, parse_mode="HTML", reply_markup=reply_markup)
        else:
            await query.message.reply_text("❌ Erreur lors du chargement des détails du personnage.", parse_mode="HTML")

# ──────────────────────────
# Messages & erreurs
# ──────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type in ["group", "supergroup"]:
        if context.bot.username and f"@{context.bot.username}" in update.message.text:
            # Extraire le query après la mention du bot
            query = update.message.text.replace(f"@{context.bot.username}", "").strip()
            if query:
                await perform_search(update, query, context)
            else:
                await update.message.reply_text("❌ Veuillez spécifier un anime après la mention.", parse_mode="HTML")
        return

    query = (update.message.text or "").strip()
    if query:
        await perform_search(update, query, context)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Erreur lors du traitement de la mise à jour {update}: {context.error}")
    try:
        if update and getattr(update, "message", None):
            await update.message.reply_text("❌ Une erreur s'est produite. Veuillez réessayer plus tard.", parse_mode="HTML")
    except Exception:
        pass

# ──────────────────────────
# Lancement
# ──────────────────────────
def main():
    if not TOKEN:
        raise RuntimeError("La variable d'environnement TOKEN est manquante.")
    app = Application.builder().token(TOKEN).build()

    # Commandes
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("aide", help_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("recherche", search_command))
    app.add_handler(CommandHandler("anime", anime_command))
    app.add_handler(CommandHandler("saison", season_command))
    app.add_handler(CommandHandler("personnage", character_command))
    app.add_handler(CommandHandler("character", character_command))  # alias
    app.add_handler(CommandHandler("top", top_command))
    app.add_handler(CommandHandler("random", random_command))
    app.add_handler(CommandHandler("planning", planning_command))

    # Inline & messages
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Erreurs
    app.add_error_handler(error_handler)

    print("✅ Bot anime lancé…")
    app.run_polling()

if __name__ == "__main__":
    main()
