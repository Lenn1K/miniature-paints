from .ak import AKScraper
from .army_painter import ArmyPainterScraper
from .gsw import GreenStuffWorldScraper
from .vallejo import VallejoScraper

SCRAPERS = {s.brand_slug: s for s in (VallejoScraper, AKScraper, ArmyPainterScraper, GreenStuffWorldScraper)}
