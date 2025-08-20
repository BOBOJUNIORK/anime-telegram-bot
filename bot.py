import os
import re
import math
import logging
import html
import requests

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
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# ──────────────────────────
# Token via variable d’environnement
# (sur Render: Settings > Environment > KEY=TOKEN, VALUE=ton_token)
# ──────────────────────────
TOKEN = os.getenv("TOKEN")  # ne laisse pas ton token en clair dans le code !

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

def format_character_info(character):
    name = escape_html(decode_html_entities(character.get("name", "Nom inconnu")))
    name_kanji = escape_html(decode_html_entities(character.get("name_kanji", "")))
    about = decode_html_entities(character.get("about", "Pas d'informations disponibles"))
    try:
        if about and about != "Pas d'informations disponibles":
            about_short = truncate(about, 800)
            about_fr = GoogleTranslator(source="auto", target="fr").translate(about_short)
        else:
            about_fr = about
    except Exception as e:
        logger.error(f"Erreur de traduction personnage: {e}")
        about_fr = about

    about_fr = escape_html(about_fr)
    title = f"{name} ({name_kanji})" if name_kanji else name
    return f"👤 <b>{title}</b>\n\n📝 <b>Description</b>:\n{about_fr}"

# ──────────────────────────
# Liens de streaming
# ──────────────────────────
def generate_watch_links(anime_title):
    """Génère des liens de recherche vers les sites de streaming français"""
    encoded_title = requests.utils.quote(anime_title)
    
    sites = [
        ("VoirAnime", f"https://voiranime.com/?s={encoded_title}"),
        ("Anime-Sama", f"https://www.anime-sama.fr/search/?q={encoded_title}"),
        ("French-Anime", f"https://french-anime.com/search?q={encoded_title}"),
        ("Franime", f"https://franime.fr/?s={encoded_title}"),
        ("Anime-Ultime", f"https://www.anime-ultime.net/search-0-0-{encoded_title}.html"),
    ]
    
    return sites

def format_streaming_links(anime):
    """Formate les liens de streaming pour l'anime"""
    titre = escape_html(decode_html_entities(anime.get("title", "Titre inconnu")))
    
    # Générer les liens de recherche
    streaming_links = generate_watch_links(anime.get("title", ""))
    
    # Créer le texte avec les liens
    text = f"📺 <b>Regarder {titre}</b>:\n\n"
    text += "Voici où vous pourriez trouver cet anime:\n\n"
    
    for site_name, url in streaming_links:
        text += f"• <a href='{escape_html(url)}'>{escape_html(site_name)}</a>\n"
    
    text += "\n🔍 <i>Note: Ces liens mènent à des pages de recherche. La disponibilité peut varier.</i>"
    
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
            InlineKeyboardButton("🎯 Similaires", callback_data=f"similar_{anime_id}"),
            InlineKeyboardButton("📺 Streaming", callback_data=f"streaming_{anime_id}"),
        ],
    ]
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
        "• 👥 Fonctionne dans les groupes et en privé\n\n"
        "💡 <b>Commandes disponibles :</b>\n"
        "• Tapez le nom d'un anime pour le rechercher\n"
        "• <code>/saison &lt;année&gt; &lt;saison&gt;</code> (ex : <code>/saison 2023 fall</code>)\n"
        "• <code>/personnage &lt;nom&gt;</code> (ex : <code>/personnage Naruto</code>)\n"
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
        "🎯 <b>Navigation interactive :</b>\n"
        "• Boutons : Synopsis, Détails, Studio, Trailer, Similaires\n\n"
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

# ──────────────────────────
# Affichages
# ──────────────────────────
async def display_character_info(update_or_query, character):
    image_url = character["images"]["jpg"]["image_url"]
    info_text = format_character_info(character)

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
            # En cas d'édition, on renvoie un nouveau message si l’API refuse l’edit
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
            streaming_text = format_streaming_links(anime)
            
            # Créer un clavier avec des boutons de liens
            streaming_links = generate_watch_links(anime.get("title", ""))
            keyboard = []
            for site_name, url in streaming_links:
                keyboard.append([InlineKeyboardButton(site_name, url=url)])
            
            # Ajouter un bouton retour
            keyboard.append([InlineKeyboardButton("🔙 Retour", callback_data=f"anime_{anime_id}")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.message.reply_text(streaming_text, parse_mode="HTML", reply_markup=reply_markup)
        else:
            await query.message.reply_text("❌ Impossible de charger les liens de streaming.", parse_mode="HTML")

# ──────────────────────────
# Messages & erreurs
# ──────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type in ["group", "supergroup"]:
        if context.bot.username and f"@{context.bot.username}" in update.message.text:
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

    # Inline & messages
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Erreurs
    app.add_error_handler(error_handler)

    print("✅ Bot anime lancé…")
    app.run_polling()

if __name__ == "__main__":
    main()
