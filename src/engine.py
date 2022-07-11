import os
import json
import time
from retry import retry
from urllib.parse import quote_plus

from selenium import webdriver
from selenium.webdriver.common import keys
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

import pymongo
import pandas as pd
import requests
from bs4 import BeautifulSoup

class Engine:

    def __init__(self):
        self.options = Options()
        self.options.headless = True
        self.driver = webdriver.Firefox(options=self.options)
        self.bot = self.driver
        
        self.mongourl = os.environ['mongourl']
        username = quote_plus(os.environ['username'])
        password = quote_plus(os.environ['password'])
        uri = 'mongodb+srv://' + username + ':' + password + '@' + self.mongourl + '/?retryWrites=true&w=majority'
        self.client = pymongo.MongoClient(uri)
        self.db = self.client['crawler-db']
        
        with open("./src/sources.json", "r") as f:
            self.source = json.load(f)
            
        print(time.ctime(),'. Scrapper Initialized') 
        
    def update_rates(self):
        deposit_values = {}
        credit_values = pd.DataFrame()
        print('Started to scrape data...')
        for short_name in self.source.keys():
            deposit_values[short_name] = self.get_deposit_rates(short_name)
            for maturity in [3,6,9,12,18,24,30,36]:
                credit_values = self.get_interest_rates(short_name,maturity,self.source,credit_values)
                
        self.db['loan-collection'].drop()
        self.db['deposit-collection'].drop()
        self.db['loan-collection'].insert_one({
            "index":"loan-data",
            "data":credit_values.to_dict("records")
        })
        self.db['deposit-collection'].insert_one({
            "index":"deposit-data",
            "data":deposit_values
        })
        print(time.ctime(),'. Scrapped data and updated database!') 
        
    def read_rates(self,collection):
        result_data = list(self.db[collection].find())[0]['data']
        return result_data
        
    @retry(tries=3, delay=10)
    def get_deposit_rates(self,short_name):
        def col_fixer(col,allcols):
            allcols = [col.replace(' ','').replace('Gün','') for col in allcols]
            col = col.replace(' ','').replace('Gün','')
            if col.isdigit():
                col_idx = allcols.index(col)
                if col_idx==1:
                    col = "1-"+col
                elif col_idx>1:
                    if allcols[col_idx-1].isdigit():
                        col = str(int(allcols[col_idx-1])+1)+"-"+col
                    elif '-' in allcols[col_idx-1]:
                        last = allcols[col_idx-1].split('-')[1]
                        col = str(int(last)+1)+"-"+col
                    
            return col
        
        page = requests.get(f'https://www.hangikredi.com/yatirim-araclari/mevduat-faiz-oranlari/{short_name}').text
        soup = BeautifulSoup(page, "html.parser")

        tableInner = soup.findAll('table', attrs={"class" : "deposit-interest-table__inner"})
        deposit_values_tmp = pd.DataFrame()
        deposit_vals = []
        for table in tableInner:
            deposit_vals.append(pd.read_html(table.prettify())[0])
        if len(deposit_vals)>0:
            deposit_values_tmp = pd.merge(deposit_vals[0],deposit_vals[1],left_index=True,right_index=True)
            deposit_values_tmp.columns = [col_fixer(col,list(deposit_values_tmp.columns)) for col in deposit_values_tmp.columns]
            deposit_values_tmp['AnaPara'] = deposit_values_tmp['AnaPara'].apply(lambda x: int(x.replace(' ','').replace('TL','').replace('.','').split('-')[1]))

            deposit_values_tmp = deposit_values_tmp.replace(" ","", regex=True)
            deposit_values_tmp = deposit_values_tmp.replace("-",0, regex=True)
            deposit_values_tmp = deposit_values_tmp.replace(",",".", regex=True)
            deposit_values_tmp = deposit_values_tmp.replace("%","", regex=True)

        print(time.ctime(),'. Scraped deposit rates from source',short_name)
        return json.loads(deposit_values_tmp.to_json(orient='records'))
        
    @retry(tries=3, delay=10)
    def get_interest_rates(self,short_name,maturity,credit_source,credit_values):
        bot = self.bot
        wait = WebDriverWait(bot, 60)
        
        credit_values_tmp = credit_values.copy()
        url_credit = credit_source[short_name]['url_credit']
        amount_range = credit_source[short_name]['amount_range_credit']

        for amount_max in amount_range:
            if ((amount_max>=100000 and maturity>12) or
                (amount_max>=50000 and maturity>24)):
                continue
            try:
                bot.get('https://www.hangikredi.com/kredi/ihtiyac-kredisi/'+short_name)

                locator = (By.XPATH,'//*[@id="bank-interest-rates-list"]/table[1]/tbody[1]/tr[1]/td[1]/div[1]/span[1]')
                amount = wait.until(EC.visibility_of_element_located(locator))
                amount = amount.text.replace(' ','').replace('.','').replace('TL','').split('-')
                min_amount = int(amount[0])
                max_amount = int(amount[1])                    

                locator = (By.XPATH,'//*[@id="bank-interest-rates-list"]/table[1]/tbody[1]/tr[1]/td[2]/div[1]/span[1]')
                maturity_range = wait.until(EC.visibility_of_element_located(locator))
                maturity_range = maturity_range.text.replace(' ','').replace('Ay','').split('-')
                min_maturity = int(maturity_range[0])
                max_maturity = int(maturity_range[1])

                if min_maturity <= maturity <=max_maturity:
                    bot.get(url_credit+f'amount={amount_max}&maturity={maturity}')

                    locator = (By.XPATH,'//*[@id="pfc__graph-and-details"]/div[1]/div[2]/div[2]/div[1]/dl[1]/dd[1]')
                    interest_rate = wait.until(EC.visibility_of_element_located(locator))
                    interest_rate = float(interest_rate.text.replace(' ','').replace('%','').replace(',','.'))

                    locator = (By.XPATH,'//*[@id="pfc__graph-and-details"]/div[1]/div[2]/div[2]/div[1]/dl[1]/dd[6]')
                    fee = wait.until(EC.visibility_of_element_located(locator))
                    fee = float(fee.text.replace(' ','').replace('.','').replace('TL','').replace(',','.'))
                    fee_pct = (fee/amount_max)*100

                    if credit_values_tmp.shape[0]==0:
                        credit_values_tmp = pd.DataFrame({'bank':short_name,
                                                          'amount_range_limit': amount_max, 
                                                          'maturity': maturity,
                                                          'interest_rate':interest_rate,
                                                          'min_amount':min_amount,
                                                          'max_amount':max_amount,
                                                          'min_maturity':min_maturity,
                                                          'max_maturity':max_maturity,
                                                          'fee_pct':fee_pct},index=[0])
                    else:
                        tmpDF = pd.DataFrame({'bank':short_name,
                                              'amount_range_limit': amount_max, 
                                              'maturity': maturity,
                                              'interest_rate':interest_rate,
                                              'min_amount':min_amount,
                                              'max_amount':max_amount,
                                              'min_maturity':min_maturity,
                                              'max_maturity':max_maturity,
                                              'fee_pct':fee_pct},index=[0])
                        credit_values_tmp = pd.concat([credit_values_tmp,tmpDF],ignore_index=True)
            except:
                print("Error:",short_name,maturity,amount_max,"is not supported!")
        print(time.ctime(),'. Scraped loan rates from source', short_name, maturity)
        return credit_values_tmp
