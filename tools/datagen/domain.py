"""Apparel / fast-fashion domain vocabulary.

Deliberately opinionated: real-sounding part names and sourcing geography so
the extracted graph reads plausibly. All lists are kept small so the full
seedable combinatorics stay stable across runs.
"""
from __future__ import annotations

# --- Sourcing geography ---------------------------------------------------
# Country, ISO2, dominant currency used in local invoices (mess injector
# sometimes swaps these).
COUNTRIES: list[tuple[str, str, str]] = [
    ("Bangladesh", "BD", "BDT"),
    ("Vietnam",    "VN", "VND"),
    ("India",      "IN", "INR"),
    ("China",      "CN", "CNY"),
    ("Turkey",     "TR", "TRY"),
    ("Portugal",   "PT", "EUR"),
    ("Cambodia",   "KH", "KHR"),
    ("Indonesia",  "ID", "IDR"),
    ("Pakistan",   "PK", "PKR"),
    ("Sri Lanka",  "LK", "LKR"),
    ("Morocco",    "MA", "MAD"),
    ("Tunisia",    "TN", "TND"),
    ("Mexico",     "MX", "MXN"),
    ("Honduras",   "HN", "HNL"),
    ("Peru",       "PE", "PEN"),
    ("Italy",      "IT", "EUR"),
    ("Spain",      "ES", "EUR"),
    ("Egypt",      "EG", "EGP"),
    ("Myanmar",    "MM", "MMK"),
    ("Ethiopia",   "ET", "ETB"),
]

# Representative apparel ports by country.
PORTS: dict[str, list[str]] = {
    "BD": ["Chittagong", "Mongla"],
    "VN": ["Ho Chi Minh (Cat Lai)", "Hai Phong"],
    "IN": ["Mundra", "Nhava Sheva", "Chennai"],
    "CN": ["Shanghai", "Ningbo", "Shenzhen (Yantian)"],
    "TR": ["Istanbul (Ambarli)", "Mersin"],
    "PT": ["Leixoes", "Lisbon"],
    "KH": ["Sihanoukville"],
    "ID": ["Tanjung Priok", "Semarang"],
    "PK": ["Karachi", "Port Qasim"],
    "LK": ["Colombo"],
    "MA": ["Casablanca", "Tanger Med"],
    "TN": ["Rades"],
    "MX": ["Manzanillo", "Veracruz"],
    "HN": ["Puerto Cortes"],
    "PE": ["Callao"],
    "IT": ["Genoa", "La Spezia"],
    "ES": ["Barcelona", "Valencia"],
    "EG": ["Alexandria", "Damietta"],
    "MM": ["Yangon"],
    "ET": ["Djibouti"],
}

# Destination hubs where retail distribution lands.
DESTINATION_PORTS: list[tuple[str, str]] = [
    ("Rotterdam",       "NL"),
    ("Hamburg",         "DE"),
    ("Antwerp",         "BE"),
    ("Felixstowe",      "GB"),
    ("Los Angeles",     "US"),
    ("Long Beach",      "US"),
    ("New York / NJ",   "US"),
    ("Savannah",        "US"),
    ("Vancouver",       "CA"),
    ("Yokohama",        "JP"),
]

# --- Fabric / component vocabulary ---------------------------------------
FABRIC_FIBERS = [
    "100% Cotton", "Organic Cotton", "Recycled Cotton",
    "Polyester", "Recycled Polyester", "Cotton/Polyester 60/40",
    "Cotton/Elastane 95/5", "Viscose", "Modal", "Lyocell (Tencel)",
    "Linen", "Linen/Cotton 55/45", "Nylon", "Nylon/Elastane 85/15",
    "Wool blend", "Merino Wool", "Cashmere blend", "Acrylic",
    "Denim 12oz", "Denim 10oz", "Denim 14oz", "Chambray",
    "French Terry", "Fleece", "Jersey Knit", "Interlock Knit",
    "Poplin", "Twill", "Oxford", "Satin",
]

TRIMS = [
    "YKK zipper #5", "YKK zipper #3", "Riri zipper",
    "Horn button 18L", "Horn button 24L", "Resin button 20L",
    "Snap button nickel", "Metal rivet copper",
    "Cotton thread Tex 40", "Polyester thread Tex 24",
    "Woven label (care)", "Printed label (brand)", "Hangtag",
    "Elastic waistband 40mm", "Drawcord 5mm",
    "Interlining fusible", "Shoulder pad", "Collar stay",
    "Grosgrain ribbon", "Lace trim 15mm",
]

DYES_CHEMICALS = [
    "Reactive dye - navy", "Reactive dye - black", "Reactive dye - olive",
    "Disperse dye - charcoal", "Pigment print paste - white",
    "Softener finish silicone", "Enzyme wash cellulase",
    "Potassium permanganate (bleach)", "Indigo dye vat",
]

# --- SKU vocabulary (garment types × fits × seasons) ---------------------
GARMENT_TYPES = [
    ("T-shirt",         "TSH"),
    ("Polo",            "POL"),
    ("Shirt",           "SHT"),
    ("Blouse",          "BLS"),
    ("Dress",           "DRS"),
    ("Skirt",           "SKR"),
    ("Jeans",           "JNS"),
    ("Chinos",          "CHN"),
    ("Jogger",          "JGR"),
    ("Shorts",          "SHO"),
    ("Hoodie",          "HOD"),
    ("Sweatshirt",      "SWT"),
    ("Cardigan",        "CRD"),
    ("Sweater",         "SWR"),
    ("Jacket",          "JKT"),
    ("Coat",            "COT"),
    ("Blazer",          "BLZ"),
    ("Puffer",          "PFR"),
    ("Scarf",           "SCF"),
    ("Underwear",       "UNW"),
]

FITS = ["Slim", "Regular", "Relaxed", "Oversize", "Tailored", "Cropped", "Longline"]

SIZE_RUNS = {
    "alpha":   ["XS", "S", "M", "L", "XL", "XXL"],
    "numeric": ["24", "26", "28", "30", "32", "34", "36", "38", "40"],
    "shoe":    ["36", "37", "38", "39", "40", "41", "42"],  # unused but ready
}

COLORS = [
    ("Black",      "BLK"),
    ("White",      "WHT"),
    ("Navy",       "NVY"),
    ("Charcoal",   "CHR"),
    ("Olive",      "OLV"),
    ("Khaki",      "KHK"),
    ("Camel",      "CML"),
    ("Rust",       "RST"),
    ("Burgundy",   "BRG"),
    ("Forest",     "FRS"),
    ("Powder Blue","PBL"),
    ("Blush",      "BLH"),
    ("Mustard",    "MST"),
    ("Terracotta", "TRC"),
    ("Indigo",     "IND"),
    ("Ecru",       "ECR"),
]

SEASONS = ["SS26", "AW26", "SS27"]

# --- Supplier / plant naming ---------------------------------------------
SUPPLIER_NAME_STEMS = [
    "Horizon", "Meridian", "Vanguard", "Cascade", "Summit", "Harbor",
    "Lotus", "Jasmine", "Monsoon", "Delta", "Pacific", "Orient", "Cedar",
    "Riverstone", "Blue Ridge", "Golden", "Silverline", "Iron Mill",
    "Lotus Valley", "Bluefin", "Red Thread", "Ivory Loom", "Northstar",
    "Highland", "Lowland", "Coral", "Granite", "Emerald", "Amber",
    "Sapphire", "Oakmoor", "Spindle", "Shuttle", "Warp & Weft",
    "Reed & Heald", "Needlepoint", "Cuttle", "Lustre", "Bobbin",
    "Finewoven", "Crispfibre", "Puregrain",
]

SUPPLIER_NAME_SUFFIXES = [
    "Textiles",       "Garments",     "Apparel",      "Manufacturing",
    "Industries",     "Mills",        "Fabrics",      "Knitwear",
    "Dyeing & Finishing", "Trading", "Group",         "Enterprises",
    "Co.",            "Limited",      "Pvt Ltd",      "Holdings",
    "International",  "Export House",
]

PLANT_SUFFIXES = ["Unit", "Factory", "Plant", "Mill", "Facility", "Works"]

# --- Supplier capability flags -------------------------------------------
TIER1_CAPABILITIES = ["CMT", "Full Package", "Private Label", "Finishing"]
TIER2_CAPABILITIES = ["Weaving", "Knitting", "Spinning", "Dyeing", "Printing",
                      "Trim", "Button", "Zipper", "Thread"]

CERTIFICATIONS = [
    "GOTS",       # Global Organic Textile Standard
    "OEKO-TEX Standard 100",
    "BSCI",       # Business Social Compliance Initiative
    "SA8000",
    "WRAP",       # Worldwide Responsible Accredited Production
    "ISO 9001",
    "ISO 14001",
    "Higg FEM",   # Facility Environmental Module
    "Fair Trade Certified",
    "GRS",        # Global Recycled Standard
    "BCI",        # Better Cotton Initiative
]

INCOTERMS = ["FOB", "CIF", "DDP", "EXW", "FCA", "DAP"]
