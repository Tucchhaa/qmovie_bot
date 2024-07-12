import asyncio
import nest_asyncio
from playwright.async_api import Page

from bot import Bot
from movie_fetcher import create_movie_fetcher
from scrapper import RezkaScrapper


async def main() -> None:
    hdrezka_scrapper = RezkaScrapper()

    movie_fetcher = await create_movie_fetcher([hdrezka_scrapper])

    bot = Bot(movie_fetcher)

    await bot.launch()

nest_asyncio.apply()
asyncio.run(main())

# TODO:
# 1) optimize browser requests: probably no need to load css
# 2) add more resources than just HDRezka
# 3) collect statistics
# 4) launch browsers in different thread
# 5) download series
# 6) try to enable chrome to run in headless
# 7) check if a movie is uploaded or just announced
