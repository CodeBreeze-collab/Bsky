import csv
import os
import re
import sys

INPUT_CSV = "igive_stores_verified.csv"  # or "igive_stores.csv"
OUTPUT_CSV = "igive_stores_categorized.csv"

# Comprehensive Retail Category taxonomy
CATEGORIES = {
    "Pets & Animals": [
        "pet", "dog", "cat", "vet", "chewy", "bark", "animal", "pup", "fish", "aquarium", "paws"
    ],
    "Apparel, Shoes & Fashion": [
        "apparel", "clothing", "wear", "shoes", "fashion", "boutique", "jeans", "couture", "wrangler",
        "outfitters", "dress", "shirt", "boots", "lingerie", "bra", "attire", "footwear", "jewelry",
        "watch", "gold", "diamond", "style", "tailor", "threads", "socks", "underwear", "zobha",
        "la senza", "true religion", "sebastian cruz", "hue", "athleta", "gap", "old navy", "banana republic"
    ],
    "Health, Beauty & Personal Care": [
        "beauty", "cosmetics", "pharmacy", "vitamin", "health", "skin", "hair", "wellness", "fragrance",
        "perfume", "makeup", "derma", "laser", "quasar", "tatcha", "vegamour", "clark's botanicals",
        "bath", "soap", "nutrition", "cbd", "supplement", "optic", "contacts", "lens", "eyewear"
    ],
    "Electronics, Software & Office": [
        "electronics", "tech", "computer", "software", "vpn", "photo", "audio", "mobile", "wireless",
        "ink", "toner", "print", "psprint", "camera", "gadget", "battery", "app", "cloud", "security",
        "domain", "hosting", "hardware", "office", "paper", "stationery"
    ],
    "Home, Garden & Appliances": [
        "home", "furniture", "bed", "decor", "kitchen", "mattress", "hardware", "lighting", "bath",
        "oven", "appliance", "lawn", "garden", "cub cadet", "burpee", "tools", "patio", "couch",
        "rug", "frame", "pictureframes", "blinds", "shade", "tile", "lumber"
    ],
    "Travel, Hotels & Vehicles": [
        "hotel", "resort", "travel", "flight", "airline", "cruise", "vacation", "car rental",
        "enterprise", "rent-a-car", "station casinos", "barcelo", "trip", "booking", "tour",
        "transit", "ticket", "auto", "parts", "tire", "car"
    ],
    "Food, Wine & Gifts": [
        "food", "basket", "florist", "flower", "wine", "gourmet", "snack", "meat", "bakery",
        "debragga", "sugarfina", "gift", "giftcards", "candy", "chocolate", "fruit", "coffee",
        "tea", "liquor", "spirits", "dining", "restaurant"
    ],
    "Toys, Crafts, Books & Music": [
        "michaels", "craft", "hobby", "toy", "game", "book", "music", "brasswind", "woodwind",
        "instrument", "art", "yarn", "fabric", "sewing", "collectible", "puzzle"
    ],
    "Sports, Outdoors & Fitness": [
        "sports", "outdoor", "gear", "fitness", "golf", "cycle", "hunting", "fishing", "athletics",
        "gym", "bike", "camping", "hiking", "run", "active"
    ]
}


def classify_store(store_name, igive_url, actual_url=""):
    combined_text = f"{store_name} {igive_url} {actual_url}".lower()

    for category, keywords in CATEGORIES.items():
        for kw in keywords:
            # Match word boundaries or explicit sub-strings
            if re.search(r"\b" + re.escape(kw) + r"\b", combined_text) or kw in combined_text:
                return category

    return "General Retail & Shopping"


def main():
    if not os.path.exists(INPUT_CSV):
        print(f"Error: Could not find '{INPUT_CSV}'. Please check the filename.")
        sys.exit(1)

    with open(INPUT_CSV, mode="r", encoding="utf-8") as infile:
        stores = list(csv.DictReader(infile))

    print(f"Loaded {len(stores)} stores from '{INPUT_CSV}'. Categorizing...\n")

    categorized_stores = []
    category_counts = {}

    for row in stores:
        name = row.get("store_name", "").strip()
        igive_url = row.get("igive_url", "").strip()
        actual_url = row.get("actual_store_url", "").strip()
        rate = row.get("donation_rate", "").strip()

        category = classify_store(name, igive_url, actual_url)
        category_counts[category] = category_counts.get(category, 0) + 1

        categorized_stores.append({
            "store_name": name,
            "category": category,
            "donation_rate": rate,
            "igive_url": igive_url,
            "actual_store_url": actual_url
        })

    # Sort results alphabetically by store name
    categorized_stores.sort(key=lambda x: x["store_name"].lower())

    fieldnames = ["store_name", "category", "donation_rate", "igive_url", "actual_store_url"]
    with open(OUTPUT_CSV, mode="w", newline="", encoding="utf-8") as outfile:
        writer = csv.DictWriter(outfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(categorized_stores)

    print("--- Category Breakdown Summary ---")
    for cat, count in sorted(category_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  • {cat}: {count} stores")

    print(f"\nDone! Processed {len(stores)} stores and saved to '{OUTPUT_CSV}'.")


if __name__ == "__main__":
    main()