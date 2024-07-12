import json
import sys
import traceback

from telegram.constants import ParseMode

from movie_fetcher import MovieFetcher, MovieData
import logging

from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (Application, CommandHandler, ConversationHandler,
                          ContextTypes, MessageHandler, filters, DictPersistence, PersistenceInput)

from scrapper import ScrapperResolutionNotFoundException

api_token = "7187587907:AAFpwGTsVt4J4Xxfvvkm7DupUz8hJk-S1PU"
tucha_chat_id = 500977161

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

ASK_SEARCH_RESULT, ASK_DUBBING, ASK_RESOLUTION, SEND_MOVIE = range(4)
THANK_FOR_FEEDBACK = 5


class Bot:

    def __init__(self, movie_fetcher: MovieFetcher):
        self.movie_fetcher: MovieFetcher = movie_fetcher

        persistence = DictPersistence(store_data=PersistenceInput(user_data=True, bot_data=True, chat_data=False, callback_data=False))

        self.app = (Application.builder()
                    .token(api_token)
                    .persistence(persistence)
                    .post_init(self.set_my_commands)
                    .build())

    async def set_my_commands(self, application: Application):
        await self.app.bot.set_my_commands([
            ('start', 'Начать общение-печенье'),
            ('help', 'Хелпануть немножечко'),
            ('download', 'Скачать фильм (легально)'),
            ('feedback', 'Отправить отзыв моему создателю'),
            ('cancel', 'Отменить текущее движение'),
        ])

    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        await update.message.reply_text("Упс! Произошла какая-то ошибка, разработчик оповещен и исправит проблему. Попробуй позже или поищи другой фильм", reply_markup=ReplyKeyboardRemove())

        with open(f'./errors/{datetime.now().strftime("%d-%m-%Y %H:%M:%S")}_{update.message.from_user.id}', 'w+') as file:
            exc_info = sys.exc_info()
            sExceptionInfo = traceback.format_exception(*exc_info)
            exc_type, exc_value, exc_context = exc_info

            data = {
                "type": exc_type.__name__,
                "description": str(exc_value),
                "details": sExceptionInfo,

                'update': update.to_dict() if isinstance(update, Update) else str(update),
                'user_data': context.user_data
            }

            data_json = json.dumps(data, indent=4, ensure_ascii=False, default=lambda obj: obj.to_dict() if isinstance(obj, MovieData) else obj)

            file.write(data_json)

        context.user_data.clear()

        return ConversationHandler.END

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(rf"Привет, пользователь! Хочешь скачать фильм отправь мне /download, если в какой-то момент ты понял, что ошибься отправь /cancel и начни сначала")

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(f"Я помогу тебе скачать фильм без регистрации, СМС, рекламы и прочей дряни.\n\nЧтобы скачать фильм отправь мне /download")

    async def feedback_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        await update.message.reply_text(f"Следующее твое сообщение получит автор бота: ")

        return THANK_FOR_FEEDBACK

    async def thank_for_feedback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        await update.message.reply_text("Спасибо большое за фидбек")

        await context.bot.send_message(tucha_chat_id, f"Новый фидбек: \n {update.message.text}")
        await context.bot.send_message(tucha_chat_id, f'От {update.effective_user.mention_html()}', parse_mode=ParseMode.HTML)

        return ConversationHandler.END

    async def cancel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        await update.message.reply_text("Отмен сделал, отправь /download если нужно", reply_markup=ReplyKeyboardRemove())

        return ConversationHandler.END

    async def download_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        await update.message.reply_text("Введи название фильма:")

        return ASK_SEARCH_RESULT

    async def ask_search_result(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        movie_name = update.message.text

        movies = await self.movie_fetcher.search_by_name(movie_name)
        # movies = context.user_data["search_result"]

        if len(movies) == 0:
            await update.message.reply_text("Ничего не найдено")

            return await self.download_command(update, context)

        context.user_data["movie_name"] = movie_name
        context.user_data["search_result"] = movies

        text = ""

        for i in range(len(movies)):
            movie = movies[i]

            text += f"{i+1}. {movie.name} - {movie.info} \n\n"

        reply_markup = self.create_search_result_keyboard(context)

        await update.message.reply_text(text)
        await update.message.reply_text("Выбери номер результата поиска: ", reply_markup=reply_markup)

        return ASK_DUBBING

    def create_search_result_keyboard(self, context: ContextTypes.DEFAULT_TYPE) -> ReplyKeyboardMarkup:
        n = len(context.user_data["search_result"])
        m = 3 if n <= 15 else 4
        keyboard = []

        i = 0

        while i < n:
            row = []

            for j in range(m):
                if i == n:
                    break

                i += 1
                row.append(f"{i}")

            keyboard.append(row)

        markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)

        return markup

    async def ask_dubbing(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        if not update.message.text.isnumeric():
            await update.message.reply_text("Ты ввел не число. Введи номер результата поиска: ")
            return ASK_DUBBING

        index = int(update.message.text)

        if index <= 0 or index > len(context.user_data["search_result"]):
            await update.message.reply_text("Ты ввел неверное число. Введи номер результата поиска: ")
            return ASK_DUBBING

        chosen_movie: MovieData = context.user_data["search_result"][index-1]
        chosen_movie = await self.movie_fetcher.get_movie_complete_info(chosen_movie)
        context.user_data["chosen_movie"] = chosen_movie

        reply_markup = self.create_dubbings_keyboard(chosen_movie.dubbings)

        await update.message.reply_text(f"Ты выбрал: {chosen_movie.name} - {chosen_movie.info}")
        await update.message.reply_photo(photo=chosen_movie.image_url)
        await update.message.reply_text(f"Выбери озвучку:", reply_markup=reply_markup)

        return ASK_RESOLUTION

    def create_dubbings_keyboard(self, dubbings: list[str]) -> ReplyKeyboardMarkup:
        n = len(dubbings)
        m = 2
        keyboard = []

        i = 0

        while i < n:
            row = []

            for j in range(m):
                if i == n:
                    break

                row.append(dubbings[i])
                i += 1

            keyboard.append(row)

        keyboard.append(["⬅️ Выбрать другой фильм"])

        markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)

        return markup

    async def ask_resolution(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        if update.message.text == "⬅️ Выбрать другой фильм":
            reply_markup = self.create_search_result_keyboard(context)

            await update.message.reply_text("Все все, введи номер результата поиска: ", reply_markup=reply_markup)

            return ASK_DUBBING

        chosen_movie: MovieData = context.user_data["chosen_movie"]
        chosen_dubbing = update.message.text

        if not (chosen_dubbing in chosen_movie.dubbings):
            await update.message.reply_text("Такого дубляжа нет. Выбери дубляж еще раз: ")
            return ASK_RESOLUTION

        context.user_data["chosen_dubbing"] = chosen_dubbing

        reply_markup = self.create_resolutions_keyboard(chosen_movie.resolutions)
        await update.message.reply_text(f"Выбери разрешение: ", reply_markup=reply_markup)

        return SEND_MOVIE

    def create_resolutions_keyboard(self, resolutions: list[str]) -> ReplyKeyboardMarkup:
        keyboard = [[]]

        for i in resolutions:
            keyboard[0].append(i)

        markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)

        return markup

    async def send_movie(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        chosen_movie: MovieData = context.user_data["chosen_movie"]
        chosen_dubbing = context.user_data["chosen_dubbing"]
        chosen_resolution = update.message.text

        if not (chosen_resolution in chosen_movie.resolutions):
            await update.message.reply_text("Такого разрешения нет. Выбери еще раз: ")
            return SEND_MOVIE

        await update.message.reply_text("Выполняю сложные операции, ожидай")

        try:
            link = await self.movie_fetcher.get_movie_link(chosen_movie, chosen_dubbing, chosen_resolution)
        except ScrapperResolutionNotFoundException as e:
            await update.message.reply_text(f"К сожалению разрешения {e.resolution} не оказалось на сайте. Пожалуйста выбери другое разрешение")

            reply_markup = self.create_resolutions_keyboard(chosen_movie.resolutions)
            await update.message.reply_text(f"Выбери разрешение: ", reply_markup=reply_markup)

            return SEND_MOVIE

        await update.message.reply_text(f"Ссылка на скачивание: {chosen_movie.name} - {chosen_dubbing} - {chosen_resolution}: \n {link}", reply_markup=ReplyKeyboardRemove())

        context.user_data.clear()

        return ConversationHandler.END

    def launch(self):
        download_conversation_handler = ConversationHandler(
            entry_points=[CommandHandler("download", self.download_command)],
            states={
                ASK_SEARCH_RESULT:    [MessageHandler(filters.TEXT & ~filters.COMMAND, self.ask_search_result)],
                ASK_DUBBING: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.ask_dubbing)],
                ASK_RESOLUTION:       [MessageHandler(filters.TEXT & ~filters.COMMAND, self.ask_resolution)],
                SEND_MOVIE:    [MessageHandler(filters.TEXT & ~filters.COMMAND, self.send_movie)],
            },
            fallbacks=[CommandHandler("cancel", self.cancel_command)],
            name="download movie conversation",
            persistent=True
        )

        feedback_conversation_handler = ConversationHandler(
            entry_points=[CommandHandler("feedback", self.feedback_command)],
            states={
                THANK_FOR_FEEDBACK: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.thank_for_feedback)]
            },
            fallbacks=[CommandHandler("cancel", self.cancel_command)],
            name="feedback conversation",
            persistent=True
        )

        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(CommandHandler("help", self.help_command))

        self.app.add_error_handler(self.error_handler)

        self.app.add_handler(download_conversation_handler)
        self.app.add_handler(feedback_conversation_handler)

        self.app.run_polling(allowed_updates=Update.ALL_TYPES)




