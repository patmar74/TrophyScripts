from pandas import DataFrame
import json

def to_csv(jsonPath : str, csvPath="psnp_plus_export.csv"):
    with open(jsonPath, mode="r", encoding="utf-8") as json_file:
        # returns JSON object as
        # a dictionary
        data = json.load(json_file)

    lists = data.get("lists")
    if lists is None : 
        lists = []
        temp_lists = {}
        temp_lists ["name"] = "Backlog"
        temp_lists ["games"] = data["games"]
        lists.append(temp_lists)
    # A list of all the rows needed for the csv
    # It contains a dictionary for each row
    cleanedData = []

    # Iterate through all the lists of games
    for p_list in lists:
        list_name = p_list["name"]
        gameList = p_list["games"]
        for game in gameList:
            game_row = {}
            game_row["list"] = list_name
            game_row["title"] = game["title"]
            # Get the Platform for the game. The dictionary in the Json is [key=console, value=isOnConsole]
            platform_dict: dict[str, bool] = game["platforms"]
            platforms : list[str] = []
            # Dictionaries iterator returns the keys
            for platform in platform_dict:
                if platform_dict[platform] == True:
                    platforms.append(platform)
            platform = ""
            if len(platforms) > 1:
                platform = "Multi"
            else:
                platform = platforms[0]
                if platform == "psvita":
                    platform = "Vita"
                else:
                    platform =  platform.upper()
            game_row["console"] = platform

            # Get the trophies, also a key value dictionary
            trophy_dict : dict[str, int] = game["trophies"]
            for trophy_type in trophy_dict:
                game_row[trophy_type] = "={total}-{zero}".format(total=trophy_dict[trophy_type],zero=0) 

            hasDlcStr = "no"
            if game["dlccount"] > 1:
                hasDlcStr = "yes"
            game_row["hasDlc"] = hasDlcStr
            print(game_row)
            cleanedData.append(game_row)
    # Done parsing json into our list of dictionaries.
    # Convert it to a pandas DataFrame

    # Define column order for the csv
    columnNames = ["title", "bronze",
                   "silver", "gold", "platinum", "console", "hasDlc", "list"]
    df = DataFrame.from_dict(cleanedData)
    # Reorder the columns for the csv
    ordered_df = df.reindex(columns=columnNames)

    ordered_df.to_csv(csvPath, index=False, header=True)

# Set jsonPath to the relative path to the psnp plus exported json
# By default the csv will output to the current working directory as psnp_plus_export.csv
# If you want the file named something else, add the arugment 
# csvPath="path/to/csv"
to_csv(jsonPath="psnpp-unstarted_games.json")