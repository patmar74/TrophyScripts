from tokenize import String
import requests
from bs4 import BeautifulSoup
import pandas as pd
import json
import re
import time
from requests.adapters import HTTPAdapter
from random import randint
from urllib3.util import Retry
import datetime

class PsnpTrophyAnalyzer(object):
    def __init__(self, username : String) -> None:
        self.getUserAgents()
        self.psnpBaseUrl = "https://psnprofiles.com"
        self.gameDataList = []
        self.userName = username
        retry_strategy = Retry(
            total=20,
            backoff_factor=1,
            status_forcelist=[429, 500, 501, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.http = requests.Session()
        self.http.mount("", adapter)
        self.trophyLogList = []
        self.gameLinkToInfoMap = {}

    def getUserAgents(self):
        SCRAPEOPS_API_KEY = "1bdb12dc-c6ce-4886-aeea-dfcaba4893a9"
        response = requests.get('http://headers.scrapeops.io/v1/user-agents?api_key=' + SCRAPEOPS_API_KEY)
        json_response = response.json()
        self.userAgentList = json_response.get('result', [])

    def getRandomUserAgent(self):
        random_index = randint(0, len(self.userAgentList) - 1)
        return self.userAgentList[random_index]

    def makeScraperRequest(self, Url: String):

        userAgent = self.getRandomUserAgent()
        print("Requesting URL", Url, "Using UA", userAgent)
        headers = {"User-Agent": userAgent}
        page = self.http.get(url=Url, headers=headers)
        page.raise_for_status()
        print("Waiting 1 seconds...")
        # Sleep for 1 seconds to adhere to psnp's robots.txt
        time.sleep(1)
        print("Continuing...")
        return page

    def getTrophies(self,trophyDivSoup : BeautifulSoup)-> dict:
        trophyMap = {}
        trophyMap["bronze"] = int(trophyDivSoup.find("li", class_="bronze").text)
        trophyMap["silver"] = int(trophyDivSoup.find("li", class_="silver").text)
        trophyMap["gold"] = int(trophyDivSoup.find("li", class_="gold").text) 
        return trophyMap

    def getTrophiesRemaining(self, myTrophyMap : dict, totalTrophyMap : dict)-> dict:
        trophyDiffMap = {}
        trophyDiffMap["bronze"] = "=" + str(totalTrophyMap["bronze"]) + "-" +  str(myTrophyMap["bronze"])
        trophyDiffMap["silver"] = "=" + str(totalTrophyMap["silver"]) + "-" + str(myTrophyMap["silver"])
        trophyDiffMap["gold"] =   "=" + str(totalTrophyMap["gold"])   + "-" + str(myTrophyMap["gold"])
        trophyDiffMap["platinum"] = "=" + str(totalTrophyMap["platinum"]) + "-" + str(myTrophyMap["platinum"])
        return trophyDiffMap

    def addTrophyDataForPsnpGame(self, gameEndPoint : String) -> None:
        gameInfo:GameInfo = self.gameLinkToInfoMap[gameEndPoint]
        
        print("Starting analysis of:", gameInfo.gameName)
        URL = self.psnpBaseUrl + gameEndPoint
        
        page = self.makeScraperRequest(URL)
        gamePageSoup = BeautifulSoup(page.content, "html.parser")

        firstCol = gamePageSoup.select_one("div.row > div.col-xs")
        # My trophy count is always the first instance of the class in the first column
        myTrophyCountDiv = firstCol.find("div", class_="trophy-count")
        myTrophyMap = self.getTrophies(myTrophyCountDiv)
        print("My Trophies:", myTrophyMap)

        extraColSoup = gamePageSoup.select_one("div.game-image-holder").parent
        totalTrophyCountDiv = extraColSoup.find("div", class_="trophy-count")
        totalTrophyMap = self.getTrophies(totalTrophyCountDiv)
        self.addPlatinum(firstCol, myTrophyMap, totalTrophyMap)
        trophyDataMap = self.getTrophiesRemaining(myTrophyMap, totalTrophyMap)
        trophyDataMap["gameName"] = gameInfo.getEncodedGameName()
        trophyDataMap["genre"] = self.getGenre(extraColSoup)
        trophyDataMap["console"] = gameInfo.console
        trophyDataMap["region"] = gameInfo.region
        fastAchieverTime = self.get50thFastestTime(gamePageSoup)
        trophyDataMap["50thFastestTime"] = fastAchieverTime
        trophyDataMap["hasDlc"] = self.getHasDlc(firstCol)
        trophyDataMap["gameId"] = gameInfo.gameId
        gameTimes = self.getGameTimes(extraColSoup)
        for timeKey in gameTimes:
            trophyDataMap[timeKey] = gameTimes[timeKey]

        guideData = self.getGuideData(gamePageSoup)
        # Add the guideData to the trophyDataMap
        for dataKey in guideData:
            trophyDataMap[dataKey] = guideData[dataKey]
        print("Stored Trophy Data: ", trophyDataMap)
        self.gameDataList.append(trophyDataMap)

    def getGameTimes(self, gameColumnSoup : BeautifulSoup) -> dict:
        gameTimes = {}
        # Pre-fill the dictionary with blanks just in case we don't find all values
        gameTimes['First Trophy Time'] = ""
        gameTimes['Platinum Time'] = ""
        gameTimes['100% Time'] = ""
        gameTimes['Latest Trophy Time'] = ""
        timeTable = gameColumnSoup.select_one("table.box.zebra")

        timeRows : BeautifulSoup = timeTable.find_all("tr")
        timeRow : BeautifulSoup
        for timeRow in timeRows:
            timeType = timeRow.select_one("span.small-title").text
            if(timeType != "Gap"):
                dayNobr = timeRow.select_one("span.typo-top-date > nobr")
                day = dayNobr.text.replace("\n","").strip()
                day = re.sub(r"(\d{1,2})[a-z]{2}", r"\1", day)
                
                trophyTime = timeRow.select_one("span.typo-bottom-date > nobr").text.strip()
                print(timeType, day, trophyTime)
                # Append Time to the time Type
                gameTimes[timeType + " Time"] = day + " " + trophyTime
        return gameTimes

    

    # Modifies the myTrophyMap and totalTrophyMap with the data for a platinum
    # The location of the psnp platinum data is best found relative to the firstCol so that's passed in
    def addPlatinum(self, firstColSoup: BeautifulSoup, myTrophyMap: dict, totalTrophyMap: dict):
        # The identifier for the plat/complete data is the first img with src values starting with /lib/img/icons/
        completeImageSoup = firstColSoup.find("img", src=re.compile(r"/lib/img/icons/"))
        # get the image file's name from the src value (the last element holds the file name)
        imageName = completeImageSoup["src"].split("/")[-1]
        
        hasPlatCount = 0
        myPlatCount = 0
        if imageName == "platinum-icon-off.png":
            hasPlatCount = 1
        elif imageName == "platinum-icon.png":
            hasPlatCount = 1
            myPlatCount = 1
        print("Plat Count {} / {}".format(myPlatCount, hasPlatCount))
        myTrophyMap["platinum"] = myPlatCount
        totalTrophyMap["platinum"] = hasPlatCount
        
        
    def getHasDlc(self, firstColSoup : BeautifulSoup) -> str:
        hasDlcStr = "no"
        titlesList = firstColSoup.find_all("span", class_="title")
        if(len(titlesList) > 1):
            hasDlcStr = "yes"
        print("Has DLC: " + hasDlcStr)
        return hasDlcStr

    def get50thFastestTime(self, gamePageSoup: BeautifulSoup)->String:
        clubLinkSoup = gamePageSoup.find("a", string="100% Club")
        clubUri = clubLinkSoup["href"]
        URL = self.psnpBaseUrl + clubUri
        page = self.makeScraperRequest(URL)
        soup = BeautifulSoup(page.content, "html.parser")
        fastestAchieverH3Soup = soup.find("h3", string="Fastest Achievers")
        fastTime = ""
        if fastestAchieverH3Soup is not None:
            fastestAchieverDivSoup = fastestAchieverH3Soup.parent.parent.parent
            achieverTrSoupList = fastestAchieverDivSoup.find_all("tr")
            # Get the last achiever in this list, which is the 50th one
            fastAchieverTrSoup = achieverTrSoupList[-1]
            fastTime = fastAchieverTrSoup.find("nobr").text
            rank = fastAchieverTrSoup.find("td", class_="rank").text
            if(rank != "50"):
                fastTime += "(Rank:" + rank + ")"
        print("50th Fastest Time: ", fastTime)
        return fastTime

    def getGenre(self, extraColSoup: BeautifulSoup)-> String:
        genre=""
        # Get the Td if it's either genre or genres
        genreTdSoup = extraColSoup.find("td", string=re.compile("Genres?"))
        if(genreTdSoup is not None):
            genreLinkList = genreTdSoup.parent.find_all("a")
            genreLink : BeautifulSoup
            for genreLink in genreLinkList:
                genre += genreLink.text + ", "
            # remove the final comma and space
            genre = genre[:-2]
        print("Genre: ", genre)
        return genre

    def getGuideData(self, gamePageSoup : BeautifulSoup) -> dict:
        guideData = {}

        guideASoup = gamePageSoup.select_one("div.guide-page-info > a")
        if guideASoup is None:
            print("No guide found")
            # Fill out the data as blank
            guideData["difficulty"] = ""
            guideData["playthroughs"] = ""
            guideData["duration"] = ""
        else:
            # get the guide URL from the page
            guideUri = guideASoup["href"]
            print("Guide URI:" + guideUri)
            guidePage = self.makeScraperRequest(self.psnpBaseUrl + guideUri)
            soup = BeautifulSoup(guidePage.content, "html.parser")
            overviewSoup = soup.select_one("div.overview-info")
            # This will return 3 elements in a list in the following order
            # difficulty, playthroughs, duration
            overviewSpans : list[BeautifulSoup] = overviewSoup.find_all("span", class_="typo-top")
            # Difficulty text is in the format difficulty/10 so only grab the difficulty
            difficulty = overviewSpans[0].text.split("/")[0]
            print("Difficulty: " + difficulty)
            playthroughs = overviewSpans[1].text
            print("Playthroughs: " + playthroughs)
            duration = overviewSpans[2].text
            print("Duration: " + duration)
            guideData["difficulty"] = difficulty
            guideData["playthroughs"] = playthroughs
            guideData["duration"] = duration

        return guideData

    def doAnalysis(self):
        for gameUri in self.gameLinkToInfoMap.keys():
            self.addTrophyDataForPsnpGame(gameUri)        
        df = pd.DataFrame.from_dict(self.gameDataList, )
        
        columnNames = ["gameName", "50thFastestTime", "bronze", "silver", "gold", "platinum",
                       "genre", "console", "hasDlc", "difficulty", "playthroughs", "duration", "First Trophy Time", "Platinum Time", "100% Time", "Latest Trophy Time", "gameId", "region"]
        orderedDf = df.reindex(columns=columnNames)
        orderedDf.to_csv (self.userName + '.csv', index = False, header=True)
        
    
    def getTrophyLog(self, lastTrophyLogged):
        userBaseUrl = self.psnpBaseUrl + "/" + self.userName
        
        pageNum = 1
        keepIterating = True
        print("Retrieving trophy log...")
        while(keepIterating):
            userTrophyLogUrl = userBaseUrl + "/log" + "?page=" + str(pageNum)
            trophyLogPage = self.makeScraperRequest(userTrophyLogUrl)
            trophyLogPageSoup = BeautifulSoup(trophyLogPage.content, "html.parser")
            trophyLogTbody= trophyLogPageSoup.select_one("table")
            trophyLogRows = trophyLogTbody.find_all("tr")
            
            for trophyLogRow in trophyLogRows:
                trophyNumber = trophyLogRow.select_one("td:nth-child(5) > b:nth-child(1)").text[1:].replace(",", "")
                trophyNumberInt = int(trophyNumber)
                if trophyNumberInt == lastTrophyLogged:
                    print("Trophy Number matches lastTrophyLogged:" + str(lastTrophyLogged) + " Trophy Log Evaluation stopping...")
                    keepIterating = False
                    break
                # No more trophies so don't go to the next page
                if(trophyNumberInt == 1):
                    keepIterating = False
                trophyName = trophyLogRow.select_one("td:nth-child(3) > a:nth-child(1)").text
                trophyNumber = trophyLogRow.select_one("td:nth-child(5) > b:nth-child(1)").text[1:].replace(",", "")
                dateRegExPattern =  re.compile(r"^(\d+)\w+\s+(.+)")

                trophyDateRaw =  trophyLogRow.select_one("td:nth-child(6) > span:nth-child(1) > span:nth-child(1) > nobr:nth-child(1)").text
                dateMatch =  dateRegExPattern.match(trophyDateRaw)
                trophyDate = dateMatch.group(1) + " " + dateMatch.group(2)
                trophyTime = trophyLogRow.select_one("td:nth-child(6) > span:nth-child(1) > span:nth-child(3) > nobr:nth-child(1)").text
                trophyDatetime = datetime.datetime.strptime(trophyDate + " " + trophyTime, r"%d %b %Y %I:%M:%S %p")
                trophyDatetimeStr = trophyDatetime.isoformat()
                trophyType = trophyLogRow.select_one("td:nth-child(10) > span:nth-child(1) > img:nth-child(1)")["title"]
                trophyASoup = trophyLogRow.select_one("td:nth-child(1) > a:nth-child(1)")
                gameUri = trophyASoup["href"]
                gameInfo:GameInfo = self.gameLinkToInfoMap[gameUri] 
                gameName = gameInfo.getEncodedGameName()

            

                trophyRowData = {}
                trophyRowData["trophyName"] = trophyName
                trophyRowData["trophyNumber"] = trophyNumber
                trophyRowData["trophyAchievedDateTime"] = trophyDatetimeStr
                trophyRowData["trophyType"] = trophyType
                trophyRowData["trophyGameId"] = gameInfo.gameId
                trophyRowData["trophyGameName"] = gameName

                self.trophyLogList.append(trophyRowData)

            pageNum += 1
        
        # write trophy log data to csv
        df = pd.DataFrame.from_dict(self.trophyLogList, )
        
        columnNames = ["trophyName", "trophyNumber", "trophyAchievedDateTime", "trophyType","trophyGameName", "trophyGameId"]
        orderedDf = df.reindex(columns=columnNames)
        orderedDf.to_csv (self.userName + '_trophyLog.csv', index = False, header=True)
    
    def loadGameInfo(self):
        userBaseUrl = self.psnpBaseUrl + "/" + self.userName
        gamelistUrlNoPage = userBaseUrl + "?ajax=1&completion=all&order=last-played&pf=all&page="
        # start with the first page
        pageNum = 1
        # continue going through pages until pageNum = 0 which is when PSNP has no
        # more pages to load
        while pageNum != 0:
            print("Evaluating Page:", pageNum)
            gamelistUrlWithPage = gamelistUrlNoPage + str(pageNum)
            gameList = self.makeScraperRequest(gamelistUrlWithPage).json()
            gameListHtml = gameList["html"]
            gameListSoup = BeautifulSoup(gameListHtml, "html.parser")
            gameTrs =  gameListSoup.find_all("tr")
            gameTr : BeautifulSoup
            for gameTr in gameTrs:
                gameLink = gameTr.find("a", class_="title")
                gameUri = gameLink["href"]
                if(len(gameUri) > 1):
                    gameInfo = GameInfo(gameUri)
                    self.gameLinkToInfoMap[gameUri] = gameInfo
                    # get game name and region info
                    gameNameRaw = gameTr.select_one("td:nth-child(2) > div:nth-child(1) > span:nth-child(1)").text.strip().replace("\n", " ")
                    gameNameParts = gameNameRaw.split("•")
                    gameInfo.gameName = gameNameParts[0].strip()
                    if len(gameNameParts) > 1:
                        gameInfo.region = gameNameParts[1]

                    # get console
                    platformDivSoup = gameTr.find("div", class_="platforms")
                    platformSoupList: list[BeautifulSoup] = platformDivSoup.find_all("span", class_="platform")
                    consoleName = ""
                    if len(platformSoupList) > 1:
                        consoleName = "Multi"
                    else:
                        consoleName = platformSoupList[0].text
                    gameInfo.console = consoleName
                    
            nextPageScriptStr = gameListSoup.find("script", string=re.compile("nextPage"))
            nextPageStatementStr = nextPageScriptStr.text
            nextPageReg  = re.compile(r"^\W*nextPage\W*=\W*(\d+)")
            match = nextPageReg.match(nextPageStatementStr)
            nextPageStr = match.group(1)
            pageNum = int(nextPageStr)

            
class GameInfo(object):
    def __init__(self, gameUri):
        self.gameName = ""
        self.gameUri = gameUri
        gameIdPattern = re.compile(r"/trophies/(\d+)")
        gameIdMatch = gameIdPattern.match(gameUri)
        self.gameId = gameIdMatch.group(1)
        self.region = ""
        self.console = ""


    def getEncodedGameName(self): 
        encodedName = self.gameName
        if len(self.region) > 0:
            encodedName += " • " + self.region
        if len(self.console) > 0:
            encodedName += " | " + self.console
        return encodedName
        

        
    

# Analyzes all aspects of a PSNProfiles user
# Args:
#   username: Case sensitive username retrieving trophies for.
#   retrieveTrophyAnalysisFl: Flag for if the trophy count and other game data are retrieved.Defaults to True. Trophy data is output to username.csv
#   retrieveTrophyLogFl: Flag for if the trophy log should be retrieved. Defaults to True. Trophy log data is output to username_trophyLog.csv
#   lastTrophyLogged: The number of the last trophy that was logged. This is a performance helper since it's unlikley the whole log is needed for each run.
#                       Defaults to 0. Trophies are retrieved in descending order and will stop being retrieved once the acquired trophy being 
#                       evaluated matches lastTrophyLogged.  
def analyze(username, retrieveTrophyAnalysisFl=True, retrieveTrophyLogFl=True, lastTrophyLogged=0):
    analyzer = PsnpTrophyAnalyzer(username)
    startTime = time.time()
    analyzer.loadGameInfo()
    if(retrieveTrophyAnalysisFl):
        analyzer.doAnalysis()
    if(retrieveTrophyLogFl):
        analyzer.getTrophyLog(lastTrophyLogged)
    endTime = time.time()
    sec = endTime - startTime
    mins = sec // 60
    sec = sec % 60
    hours = mins // 60
    mins = mins % 60
    print("\nFinished analysis in {0}h {1}m {2:.2f}s".format(int(hours),int(mins),sec))


analyze(username="Yunakia221", retrieveTrophyAnalysisFl=True, retrieveTrophyLogFl=True)


