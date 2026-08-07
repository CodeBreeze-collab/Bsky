import pandas as pd
import re

# Load the CSV file
df = pd.read_csv('/Users/hdon/Downloads/advertiser-directory-pets.csv')

# 1. Filter out 'n/a' or missing averagePaymentTime
valid_payment_time = (
        df['averagePaymentTime'].notna() &
        ~df['averagePaymentTime'].astype(str).str.strip().str.lower().isin(['n/a', 'nan', ''])
)

# 2. Filter for paymentStatus == 'green'
is_green_status = df['paymentStatus'].astype(str).str.strip().str.lower() == 'green'

# 3. Filter for descriptions containing "vegan" (case-insensitive)
has_vegan = df['descriptionShort'].astype(str).str.contains('pets', case=False, na=False)

# Apply all three filters
filtered_df = df[valid_payment_time & is_green_status & has_vegan]

AFFILIATE_ID = "2811998"

# Print results
for index, row in filtered_df.iterrows():
    logo_url = str(row['logoUrl'])
    match = re.search(r'/profile/(\d+)\.png', logo_url)

    adv_id = match.group(1) if match else str(row['advertiserId'])
    profile_url = f"https://ui.awin.com/awin/affiliate/{AFFILIATE_ID}/merchant-profile/{adv_id}"

    print(f"Name: {row['programmeName']}")
    print(f"Payment Status: {row['paymentStatus']}")
    print(f"Average Payment Time: {row['averagePaymentTime']}")
    print(f"Image URL: {logo_url}")
    print(f"Profile URL: {profile_url}")
    print(f"Description: {row['descriptionShort']}\n")