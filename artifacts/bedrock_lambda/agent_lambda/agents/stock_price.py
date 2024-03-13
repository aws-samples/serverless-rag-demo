import yfinance as yf
import pandas as pd
from datetime import datetime


ticker = 'NVDA'

def get_stock_template(ticker: str):
    


    # Get the data for the past six months
    start_date = pd.Timestamp.today() - pd.Timedelta(days=90)
    end_date = pd.Timestamp.today()
    
    # Download the stock data
    stock_data = yf.download(ticker, start=start_date, end=end_date)
    
    current_year = datetime.now().year
    
    stock_info = yf.Ticker(ticker)
    
    stock_analysis_template = f'''<dividends>
                                    Last 5 year dividend history:
                                    {stock_info.dividends.filter(like=f'{current_year}', axis=0).to_string()}
                                    {stock_info.dividends.filter(like=f'{current_year-1}', axis=0).to_string()}
                                    {stock_info.dividends.filter(like=f'{current_year-2}', axis=0).to_string()}
                                    {stock_info.dividends.filter(like=f'{current_year-3}', axis=0).to_string()}
                                    {stock_info.dividends.filter(like=f'{current_year-4}', axis=0).to_string()}
                                </dividends>
                                <splits>
                                    Last 10 year stock splits:
                                    {stock_info.splits.filter(like=f'{current_year}', axis=0).to_string()}
                                    {stock_info.splits.filter(like=f'{current_year-1}', axis=0).to_string()}
                                    {stock_info.splits.filter(like=f'{current_year-2}', axis=0).to_string()}
                                    {stock_info.splits.filter(like=f'{current_year-3}', axis=0).to_string()}
                                    {stock_info.splits.filter(like=f'{current_year-4}', axis=0).to_string()}
                                    {stock_info.splits.filter(like=f'{current_year-5}', axis=0).to_string()}
                                    {stock_info.splits.filter(like=f'{current_year-6}', axis=0).to_string()}
                                    {stock_info.splits.filter(like=f'{current_year-7}', axis=0).to_string()}
                                    {stock_info.splits.filter(like=f'{current_year-8}', axis=0).to_string()}
                                    {stock_info.splits.filter(like=f'{current_year-9}', axis=0).to_string()}
                                    {stock_info.splits.filter(like=f'{current_year-10}', axis=0).to_string()}
                                </splits>
                                <capital_gains>
                                    Last 5 year capital gains history:
                                    {stock_info.capital_gains.filter(like=f'{current_year}', axis=0).to_string()}
                                    {stock_info.capital_gains.filter(like=f'{current_year-1}', axis=0).to_string()}
                                    {stock_info.capital_gains.filter(like=f'{current_year-2}', axis=0).to_string()}
                                    {stock_info.capital_gains.filter(like=f'{current_year-3}', axis=0).to_string()}
                                    {stock_info.capital_gains.filter(like=f'{current_year-4}', axis=0).to_string()}
                                    {stock_info.capital_gains.filter(like=f'{current_year-5}', axis=0).to_string()}
                                    {stock_info.capital_gains.filter(like=f'{current_year-6}', axis=0).to_string()}
                                    {stock_info.capital_gains.filter(like=f'{current_year-7}', axis=0).to_string()}
                                    {stock_info.capital_gains.filter(like=f'{current_year-8}', axis=0).to_string()}
                                    {stock_info.capital_gains.filter(like=f'{current_year-9}', axis=0).to_string()}
                                    {stock_info.capital_gains.filter(like=f'{current_year-10}', axis=0).to_string()}
                                    
                                </capital_gains>
                                <income_stmt>
                                    Last 4 year income statement history:
                                    {stock_info.income_stmt.to_string()}
                                </income_stmt>
                                <balance_sheet>
                                    Last 4 year balance sheet history:
                                    {stock_info.balance_sheet.to_string()}
                                </balance_sheet>
                                <recommendations>
                                {stock_info.recommendations.to_string()}
                                </recommendations>
                                <upgrades>
                                {stock_info.upgrades_downgrades.filter(like=f'{current_year}', axis=0).to_string()}
                                </upgrades>
                                <stock_price>
                                {stock_data.to_string()}
                                </stock_price>
    '''

    return stock_analysis_template



