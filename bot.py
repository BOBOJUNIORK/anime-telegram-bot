from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import requests
from deep_translator import GoogleTranslator
import logging
import html
import math
import os

# Configuration du logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TOKEN")

# ----------------------------
# Fonction de décodage HTML
# ----------------------------
def decode_html_entities(text: str) -> str:
    """Décoder toutes les entités HTML (&amp;, &#x27;, etc.)."""
    if not text:
        return ""
    return html.unescape(text)

# ----------------------------
# Fonctions API Jikan
# ----------------------------

# Fonction pour rechercher un anime via Jikan
def search_anime(query, limit=10):
    url = f"https://api.jikan.moe/v4/anime?q={query}&limit={limit}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data["data"]:
                return data["data"]
            else:
                return None
        else:
            logger.error(f"Erreur API Jikan: {response.status_code}")
            return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Erreur de connexion: {e}")
        return None

# Fonction pour obtenir les détails d'un anime par ID
def get_anime_by_id(anime_id):
    url = f"https://api.jikan.moe/v4/anime/{anime_id}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return response.json()["data"]
        else:
            return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Erreur de connexion: {e}")
        return None

# Fonction pour obtenir les animes d'une saison
def get_anime_by_season(year, season):
    url = f"https://api.jikan.moe/v4/seasons/{year}/{season}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return data["data"][:20]  # Limiter à 20 résultats
        else:
            logger.error(f"Erreur API Jikan: {response.status_code}")
            return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Erreur de connexion: {e}")
        return None

# Fonction pour rechercher des personnages
def search_character(query, limit=10):
    url = f"https://api.jikan.moe/v4/characters?q={query}&limit={limit}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data["data"]:
                return data["data"]
            else:
                return None
        else:
            logger.error(f"Erreur API Jikan: {response.status_code}")
            return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Erreur de connexion: {e}")
        return None

# Fonction pour obtenir des recommandations basées sur les genres
def get_anime_recommendations(genres, exclude_id, limit=5):
    # Convertir les objets genre en IDs pour la recherche
    genre_ids = [str(genre["mal_id"]) for genre in genres[:2]]  # Prendre les 2 premiers genres
    genre_query = ",".join(genre_ids)
    
    url = f"https://api.jikan.moe/v4/anime?genres={genre_query}&limit={limit + 1}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            # Exclure l'anime actuel des recommandations
            recommendations = [anime for anime in data["data"] if anime["mal_id"] != exclude_id]
            return recommendations[:limit]
        else:
            return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Erreur de connexion pour les recommandations: {e}")
        return None

# ----------------------------
# Fonctions de formatage
# ----------------------------

# Formater les informations de base de l'anime (pour la photo)
def format_anime_basic_info(anime):
    titre = decode_html_entities(anime.get("title", "Titre inconnu"))
    titre_japonais = decode_html_entities(anime.get("title_japanese", "N/A"))
    score = anime.get("score", "N/A")
    episodes = anime.get("episodes", "Inconnu")
    status = decode_html_entities(anime.get("status", "Inconnu"))
    year = anime.get("year", "N/A")
    
    caption = (
        f"🎌 *{titre}*"
        f"{' (' + titre_japonais + ')' if titre_japonais != 'N/A' else ''}\n\n"
        f"⭐ *Note*: {score}/10\n"
        f"📺 *Épisodes*: {episodes}\n"
        f"📊 *Statut*: {status}\n"
        f"📅 *Année*: {year}\n\n"
        f"👇 *Utilisez les boutons pour plus d'infos*"
    )
    
    return caption[:1020] + "..." if len(caption) > 1024 else caption

# Formater le synopsis
def format_synopsis(anime):
    titre = decode_html_entities(anime.get("title", "Titre inconnu"))
    synopsis = decode_html_entities(anime.get("synopsis", "Pas de synopsis disponible"))
    
    # Traduire le synopsis en français
    try:
        if synopsis and synopsis != "Pas de synopsis disponible":
            synopsis_short = synopsis[:800] + "..." if len(synopsis) > 800 else synopsis
            synopsis_fr = GoogleTranslator(source="auto", target="fr").translate(synopsis_short)
            synopsis_fr = decode_html_entities(synopsis_fr)
        else:
            synopsis_fr = synopsis
    except Exception as e:
        logger.error(f"Erreur de traduction: {e}")
        synopsis_fr = synopsis
    
    return f"📝 *Synopsis de {titre}*:\n\n{synopsis_fr}"

# Formater les détails techniques
def format_details(anime):
    titre = decode_html_entities(anime.get("title", "Titre inconnu"))
    rating = decode_html_entities(anime.get("rating", "N/A"))
    duration = anime.get("duration", "N/A")
    source = decode_html_entities(anime.get("source", "N/A"))
    genres = ", ".join([decode_html_entities(genre["name"]) for genre in anime.get("genres", [])])
    
    return (
        f"🔍 *Détails de {titre}*:\n\n"
        f"🎭 *Genres*: {genres}\n"
        f"⏱️ *Durée par épisode*: {duration}\n"
        f"📚 *Source*: {source}\n"
        f"🔞 *Classification*: {rating}"
    )

# Formater les infos studio
def format_studio_info(anime):
    titre = decode_html_entities(anime.get("title", "Titre inconnu"))
    studios = [decode_html_entities(studio["name"]) for studio in anime.get("studios", [])]
    producers = [decode_html_entities(producer["name"]) for producer in anime.get("producers", [])]
    
    studio_text = ", ".join(studios) if studios else "Inconnu"
    producer_text = ", ".join(producers[:3]) if producers else "Inconnu"
    
    return (
        f"🏢 *Infos production de {titre}*:\n\n"
        f"🎬 *Studio(s)*: {studio_text}\n"
        f"👔 *Producteur(s)*: {producer_text}"
    )

# Formater les infos personnage
def format_character_info(character):
    name = decode_html_entities(character.get("name", "Nom inconnu"))
    name_kanji = decode_html_entities(character.get("name_kanji", ""))
    about = decode_html_entities(character.get("about", "Pas d'informations disponibles"))
    
    # Traduire la description en français
    try:
        if about and about != "Pas d'informations disponibles":
            about_short = about[:800] + "..." if len(about) > 800 else about
            about_fr = GoogleTranslator(source="auto", target="fr").translate(about_short)
            about_fr = decode_html_entities(about_fr)
        else:
            about_fr = about
    except Exception as e:
        logger.error(f"Erreur de traduction personnage: {e}")
        about_fr = about
    
    return (
        f"👤 *{name}*"
        f"{' (' + name_kanji + ')' if name_kanji else ''}\n\n"
        f"📝 *Description*:\n{about_fr}"
    )

# ----------------------------
# Fonctions de navigation
# ----------------------------

# Créer les boutons de navigation pour un anime
def create_anime_navigation_keyboard(anime_id, current_page=0, total_results=0):
    keyboard = []
    
    # Première ligne - informations détaillées
    row1 = [
        InlineKeyboardButton("📝 Synopsis", callback_data=f"synopsis_{anime_id}"),
        InlineKeyboardButton("🔍 Détails", callback_data=f"details_{anime_id}")
    ]
    keyboard.append(row1)
    
    # Deuxième ligne - production et trailer
    row2 = [
        InlineKeyboardButton("🏢 Studio", callback_data=f"studio_{anime_id}"),
        InlineKeyboardButton("🎬 Trailer", callback_data=f"trailer_{anime_id}")
    ]
    keyboard.append(row2)
    
    # Troisième ligne - recommandations
    row3 = [InlineKeyboardButton("🎯 Animes similaires", callback_data=f"similar_{anime_id}")]
    keyboard.append(row3)
    
    return InlineKeyboardMarkup(keyboard)

# Créer la pagination pour les résultats de recherche
def create_search_pagination_keyboard(results, current_page=0, query="", search_type="anime"):
    keyboard = []
    items_per_page = 5
    total_pages = math.ceil(len(results) / items_per_page)
    
    start_idx = current_page * items_per_page
    end_idx = min(start_idx + items_per_page, len(results))
    
    # Boutons pour les résultats de la page actuelle
    for i in range(start_idx, end_idx):
        item = results[i]
        if search_type == "anime":
            title = decode_html_entities(item.get("title", "Sans titre"))
            item_id = item.get("mal_id")
            callback_prefix = "anime"
        else:  # character
            title = decode_html_entities(item.get("name", "Sans nom"))
            item_id = item.get("mal_id")
            callback_prefix = "character"
            
        if len(title) > 35:
            title = title[:32] + "..."
        keyboard.append([InlineKeyboardButton(title, callback_data=f"{callback_prefix}_{item_id}")])
    
    # Boutons de navigation si nécessaire
    if total_pages > 1:
        nav_row = []
        if current_page > 0:
            nav_row.append(InlineKeyboardButton("⬅️", callback_data=f"page_{search_type}_{query}_{current_page-1}"))
        
        nav_row.append(InlineKeyboardButton(f"{current_page + 1}/{total_pages}", callback_data="noop"))
        
        if current_page < total_pages - 1:
            nav_row.append(InlineKeyboardButton("➡️", callback_data=f"page_{search_type}_{query}_{current_page+1}"))
        
        keyboard.append(nav_row)
    
    return InlineKeyboardMarkup(keyboard)

# ----------------------------
# Commandes principales
# ----------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🔍 Rechercher un anime", switch_inline_query_current_chat="")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = (
        "👋 Bonjour ! Je suis votre assistant pour découvrir des animes.\n\n"
        "✨ *Fonctionnalités:*\n"
        "• 🔍 Recherche d'animes avec navigation interactive\n"
        "• 📝 Synopsis détaillés et traduits\n"
        "• 🎬 Liens vers les trailers officiels\n"
        "• 🎯 Recommandations d'animes similaires\n"
        "• 📅 Recherche par saison\n"
        "• 👤 Recherche de personnages\n"
        "• 👥 Fonctionne dans les groupes et en privé\n\n"
        "💡 *Commandes disponibles:*\n"
        "• Tapez le nom d'un anime pour le rechercher\n"
        "• `/saison <année> <saison>` (ex: /saison 2023 fall)\n"
        "• `/personnage <nom>` pour chercher un personnage\n"
        "• `/anime <nom>` ou `/recherche <nom>`"
    )
    
    await update.message.reply_text(welcome_text, parse_mode="Markdown", reply_markup=reply_markup)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "🤖 *Aide - Bot Anime Avancé*\n\n"
        "🔍 *Recherche d'animes:*\n"
        "• Tapez simplement le nom d'un anime\n"
        "• `/recherche <nom>` ou `/anime <nom>`\n\n"
        "📅 *Recherche par saison:*\n"
        "• `/saison <année> <saison>`\n"
        "• Saisons: spring, summer, fall, winter\n"
        "• Exemple: `/saison 2023 fall`\n\n"
        "👤 *Recherche de personnages:*\n"
        "• `/personnage <nom du personnage>`\n"
        "• Exemple: `/personnage Naruto`\n\n"
        "🎯 *Navigation interactive:*\n"
        "• Utilisez les boutons pour naviguer\n"
        "• Synopsis, Détails, Studio, Trailer\n"
        "• Recommandations d'animes similaires\n\n"
        "👥 *Dans les groupes:*\n"
        "• Mentionnez-moi suivi de votre recherche"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

# ----------------------------
# Nouvelles commandes
# ----------------------------

async def season_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text(
            "❌ Format incorrect. Utilisez: `/saison <année> <saison>`\n"
            "Saisons disponibles: spring, summer, fall, winter\n"
            "Exemple: `/saison 2023 fall`"
        )
        return
    
    year = context.args[0]
    season = context.args[1].lower()
    
    valid_seasons = ["spring", "summer", "fall", "winter"]
    if season not in valid_seasons:
        await update.message.reply_text(
            f"❌ Saison invalide. Utilisez: {', '.join(valid_seasons)}"
        )
        return
    
    await update.message.reply_chat_action(action="typing")
    
    results = get_anime_by_season(year, season)
    if not results:
        await update.message.reply_text(f"❌ Aucun anime trouvé pour {season} {year}.")
        return
    
    # Stocker les résultats pour la pagination
    context.user_data[f"season_results_{year}_{season}"] = results
    
    season_names = {
        "spring": "Printemps",
        "summer": "Été", 
        "fall": "Automne",
        "winter": "Hiver"
    }
    
    keyboard = create_search_pagination_keyboard(results, 0, f"{year}_{season}", "anime")
    
    await update.message.reply_text(
        f"📅 *Animes de {season_names[season]} {year}*\n"
        f"Trouvé {len(results)} anime(s). Sélectionnez celui qui vous intéresse:",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

async def character_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Veuillez spécifier un nom de personnage. Exemple: `/personnage Naruto`")
        return
    
    query = " ".join(context.args)
    await update.message.reply_chat_action(action="typing")
    
    results = search_character(query)
    if not results:
        await update.message.reply_text(f"❌ Aucun personnage trouvé pour '{query}'.")
        return
    
    # Stocker les résultats pour la pagination
    context.user_data[f"character_results_{query}"] = results
    
    if len(results) == 1:
        character = results[0]
        await display_character_info(update, character)
    else:
        keyboard = create_search_pagination_keyboard(results, 0, query, "character")
        await update.message.reply_text(
            f"👤 Personnages trouvés pour '{query}':\nSélectionnez celui qui vous intéresse:",
            reply_markup=keyboard
        )

# ----------------------------
# Fonctions d'affichage
# ----------------------------

async def display_character_info(update_or_query, character):
    image_url = character["images"]["jpg"]["image_url"]
    info_text = format_character_info(character)
    
    # Déterminer le type d'objet reçu
    if hasattr(update_or_query, 'callback_query') and update_or_query.callback_query:
        # C'est un Update avec callback_query
        message = update_or_query.callback_query.message
    elif hasattr(update_or_query, 'message') and not hasattr(update_or_query, 'callback_query'):
        # C'est un Update avec message normal
        message = update_or_query.message
    else:
        # C'est directement un CallbackQuery
        message = update_or_query.message
    
    await message.reply_photo(
        photo=image_url, 
        caption=info_text, 
        parse_mode="Markdown"
    )

async def display_anime_with_navigation(update_or_query, anime, edit_message=False):
    image_url = anime["images"]["jpg"]["large_image_url"]
    caption = format_anime_basic_info(anime)
    keyboard = create_anime_navigation_keyboard(anime["mal_id"])
    
    # Déterminer si c'est un callback_query ou un message normal
    if hasattr(update_or_query, 'callback_query') and update_or_query.callback_query:
        # C'est un Update avec callback_query
        query = update_or_query.callback_query
        message = query.message
    elif hasattr(update_or_query, 'message') and not hasattr(update_or_query, 'callback_query'):
        # C'est un Update avec message normal
        message = update_or_query.message
        query = None
    else:
        # C'est directement un CallbackQuery
        query = update_or_query
        message = query.message
    
    try:
        if edit_message and query:
            # Essayer d'éditer le message existant
            await query.edit_message_media(
                media=message.photo[-1].file_id if message.photo else image_url,
                reply_markup=keyboard
            )
            await query.edit_message_caption(
                caption=caption,
                parse_mode="Markdown",
                reply_markup=keyboard
            )
        else:
            # Envoyer un nouveau message avec photo
            await message.reply_photo(
                photo=image_url,
                caption=caption,
                parse_mode="Markdown",
                reply_markup=keyboard
            )
    except Exception as e:
        logger.error(f"Erreur lors de l'affichage de l'anime: {e}")
        # En cas d'erreur, envoyer un nouveau message
        await message.reply_photo(
            photo=image_url,
            caption=caption,
            parse_mode="Markdown",
            reply_markup=keyboard
        )

# ----------------------------
# Recherche & gestion messages
# ----------------------------
async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Veuillez spécifier un anime à rechercher. Exemple: /recherche One Piece")
        return
    query = " ".join(context.args)
    await perform_search(update, query, context)

async def anime_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Veuillez spécifier un anime. Exemple: /anime Attack on Titan")
        return
    query = " ".join(context.args)
    await perform_search(update, query, context)

async def perform_search(update: Update, query: str, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_chat_action(action="typing")
    
    results = search_anime(query)
    if not results:
        await update.message.reply_text("❌ Aucun anime trouvé. Essayez avec un autre nom.")
        return
    
    # Stocker les résultats pour la pagination dans context.user_data
    context.user_data[f"search_results_{query}"] = results
    
    if len(results) == 1:
        anime = results[0]
        await display_anime_with_navigation(update, anime)
    else:
        keyboard = create_search_pagination_keyboard(results, 0, query, "anime")
        await update.message.reply_text(
            f"🔍 {len(results)} animes trouvés pour '{query}':\nSélectionnez celui qui vous intéresse:",
            reply_markup=keyboard
        )

# ----------------------------
# Gestion des boutons inline
# ----------------------------
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    # Gestion de la pagination
    if data.startswith("page_"):
        parts = data.split("_")
        if len(parts) >= 4:
            search_type = parts[1]  # anime ou character
            search_query = "_".join(parts[2:-1])  # Reconstituer la requête qui peut contenir des underscores
            page = int(parts[-1])
            
            if search_type == "anime":
                # Rechercher dans les résultats stockés dans context.user_data
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
                
    # Affichage d'un anime spécifique
    elif data.startswith("anime_"):
        anime_id = data.split("_")[1]
        anime = get_anime_by_id(anime_id)
        
        if anime:
            await display_anime_with_navigation(query, anime)
        else:
            await query.message.reply_text("❌ Erreur lors du chargement des détails de l'anime.")
    
    # Affichage d'un personnage spécifique
    elif data.startswith("character_"):
        character_id = data.split("_")[1]
        # Chercher le personnage dans les résultats stockés
        for key, results in context.user_data.items():
            if key.startswith("character_results_"):
                character = next((c for c in results if c["mal_id"] == int(character_id)), None)
                if character:
                    await display_character_info(query, character)
                    return
        await query.message.reply_text("❌ Erreur lors du chargement des détails du personnage.")
    
    # Affichage du synopsis
    elif data.startswith("synopsis_"):
        anime_id = data.split("_")[1]
        anime = get_anime_by_id(anime_id)
        
        if anime:
            synopsis_text = format_synopsis(anime)
            await query.message.reply_text(synopsis_text, parse_mode="Markdown")
        else:
            await query.message.reply_text("❌ Impossible de charger le synopsis.")
    
    # Affichage des détails
    elif data.startswith("details_"):
        anime_id = data.split("_")[1]
        anime = get_anime_by_id(anime_id)
        
        if anime:
            details_text = format_details(anime)
            await query.message.reply_text(details_text, parse_mode="Markdown")
        else:
            await query.message.reply_text("❌ Impossible de charger les détails.")
    
    # Affichage des infos studio
    elif data.startswith("studio_"):
        anime_id = data.split("_")[1]
        anime = get_anime_by_id(anime_id)
        
        if anime:
            studio_text = format_studio_info(anime)
            await query.message.reply_text(studio_text, parse_mode="Markdown")
        else:
            await query.message.reply_text("❌ Impossible de charger les infos studio.")
    
    # Affichage du trailer
    elif data.startswith("trailer_"):
        anime_id = data.split("_")[1]
        anime = get_anime_by_id(anime_id)
        
        if anime:
            trailer_url = anime["trailer"]["url"] if anime.get("trailer") and anime["trailer"].get("url") else None
            if trailer_url:
                titre = decode_html_entities(anime.get("title", "Cet anime"))
                await query.message.reply_text(
                    f"🎬 *Trailer de {titre}*:\n\n{trailer_url}",
                    parse_mode="Markdown"
                )
            else:
                await query.message.reply_text("❌ Aucun trailer disponible pour cet anime.")
        else:
            await query.message.reply_text("❌ Impossible de charger le trailer.")
    
    # Recommandations similaires
    elif data.startswith("similar_"):
        anime_id = int(data.split("_")[1])
        anime = get_anime_by_id(anime_id)
        
        if anime and anime.get("genres"):
            recommendations = get_anime_recommendations(anime["genres"], anime_id, 5)
            if recommendations:
                keyboard = []
                for rec in recommendations:
                    title = decode_html_entities(rec.get("title", "Sans titre"))
                    if len(title) > 35:
                        title = title[:32] + "..."
                    keyboard.append([InlineKeyboardButton(title, callback_data=f"anime_{rec['mal_id']}")])
                
                reply_markup = InlineKeyboardMarkup(keyboard)
                titre_original = decode_html_entities(anime.get("title", "Cet anime"))
                await query.message.reply_text(
                    f"🎯 *Animes similaires à {titre_original}*:\n"
                    f"Basé sur les genres similaires:",
                    parse_mode="Markdown",
                    reply_markup=reply_markup
                )
            else:
                await query.message.reply_text("❌ Aucune recommandation trouvée.")
        else:
            await query.message.reply_text("❌ Impossible de charger les recommandations.")

# ----------------------------
# Gestion messages & erreurs
# ----------------------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type in ["group", "supergroup"]:
        if context.bot.username and f"@{context.bot.username}" in update.message.text:
            query = update.message.text.replace(f"@{context.bot.username}", "").strip()
            if query:
                await perform_search(update, query, context)
            else:
                await update.message.reply_text("❌ Veuillez spécifier un anime après la mention.")
        return
    
    query = update.message.text.strip()
    if query:
        await perform_search(update, query, context)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Erreur lors du traitement de la mise à jour {update}: {context.error}")
    try:
        if update and update.message:
            await update.message.reply_text("❌ Une erreur s'est produite. Veuillez réessayer plus tard.")
    except:
        pass

# ----------------------------
# Lancement du bot
# ----------------------------
def main():
    app = Application.builder().token(TOKEN).build()
    
    # Commandes de base
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("aide", help_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("recherche", search_command))
    app.add_handler(CommandHandler("anime", anime_command))
    
    # Nouvelles commandes
    app.add_handler(CommandHandler("saison", season_command))
    app.add_handler(CommandHandler("personnage", character_command))
    app.add_handler(CommandHandler("character", character_command))  # Alias en anglais
    
    # Gestionnaires
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)
    
    print("✅ Bot anime amélioré lancé avec toutes les nouvelles fonctionnalités...")
    app.run_polling()

if __name__ == "__main__":
    main()
