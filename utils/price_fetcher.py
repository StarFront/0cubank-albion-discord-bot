import aiohttp
import asyncio

async def get_item_prices(item_type_list, locations="Caerleon,Black Market,Bridgewatch,Fort Sterling,Lymhurst,Martlock,Thetford"):
    """
    Fetches prices for a list of items from the Albion Online Data Project API.
    """
    if not item_type_list:
        return {}

    # Remove duplicates to minimize URL length
    unique_items = list(set(item_type_list))
    
    # API limits URL length, so we might need to chunk if the list is huge.
    # AODP usually handles ~100 items fine.
    
    item_string = ",".join(unique_items)
    url = f"https://www.albion-online-data.com/api/v2/stats/prices/{item_string}?locations={locations}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    # Process data to find the best price (e.g., average or min sell price across cities)
                    price_map = {}
                    for entry in data:
                        item_id = entry['item_id']
                        # We can prioritize cities or just take the overall average/min
                        # Here we'll store the minimum sell price found > 0
                        sell_price = entry.get('sell_price_min', 0)
                        
                        if sell_price > 0:
                            if item_id not in price_map:
                                price_map[item_id] = sell_price
                            else:
                                price_map[item_id] = min(price_map[item_id], sell_price)
                    return price_map
                else:
                    print(f"Error fetching prices: {response.status}")
                    return {}
    except Exception as e:
        print(f"Exception fetching prices: {e}")
        return {}

async def calculate_kill_value(event):
    """
    Calculates the estimated market value of a kill event.
    """
    items_to_check = []
    
    # Helper to add items
    def add_item(item):
        if item:
            items_to_check.append(item['Type'])

    # Check Victim's Equipment
    victim = event.get('Victim', {})
    equipment = victim.get('Equipment', {})
    for part in equipment.values():
        add_item(part)

    # Check Victim's Inventory
    inventory = victim.get('Inventory', [])
    for item in inventory:
        add_item(item)

    if not items_to_check:
        return 0

    price_map = await get_item_prices(items_to_check)
    
    total_value = 0
    
    # Calculate Equipment Value
    for part in equipment.values():
        if part:
            price = price_map.get(part['Type'], 0)
            total_value += price * part.get('Count', 1)

    # Calculate Inventory Value
    for item in inventory:
        if item:
            price = price_map.get(item['Type'], 0)
            total_value += price * item.get('Count', 1)
            
    return total_value

async def get_detailed_prices(item_id, locations="Caerleon,Black Market,Bridgewatch,Fort Sterling,Lymhurst,Martlock,Thetford,Brecilien"):
    """
    Fetches detailed prices for a single item ID across locations.
    Returns a list of dictionaries: [{'city': 'Martlock', 'quality': 1, 'sell_price_min': 100, ...}, ...]
    """
    url = f"https://www.albion-online-data.com/api/v2/stats/prices/{item_id}?locations={locations}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    return []
    except Exception as e:
        print(f"Exception fetching detailed prices: {e}")
        return []

async def search_item(query):
    """
    Searches for an item by name using the Albion GameInfo API.
    """
    url = "https://gameinfo.albiononline.com/api/gameinfo/search"
    params = {"q": query}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('items', [])
                else:
                    return []
    except Exception as e:
        print(f"Exception searching item: {e}")
        return []
