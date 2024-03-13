import requests
import bs4

def weather_in(days: str, city: str):
    # Generating the url   
    url = f"https://google.com/search?q=next+{days}+days+weather+in+{city}"
    # Sending HTTP request  
    request_result = requests.get( url ) 
    # Pulling HTTP data from internet  
    soup = bs4.BeautifulSoup( request_result.text, "html.parser" ) 
  
    # Finding temperature in Celsius. 
    # The temperature is stored inside the class "BNeawe".  
    temp = soup.find( "div" , class_='BNeawe' ).text  
    return temp

ignore_sites = ['google', 'youtube']

def google_search(news):
    # Generating the url   
    url = 'https://google.com/search?q=' + news 
    # Sending HTTP request  
    request_result = requests.get( url ) 
    # Pulling HTTP data from internet  
    soup = bs4.BeautifulSoup( request_result.text, "html.parser" ) 
    #soup = bs4.BeautifulSoup( request_result.content ) 
    # print(soup.prettify()) 
  
    # Finding temperature in Celsius. 
    # The temperature is stored inside the class "BNeawe".  
    web_links = soup.select('a')
    actual_web_links = [web_link['href'] for web_link in web_links] 
    counter = 0
    template = []
    for link in actual_web_links:
        if '/url?q=https://' in link and not any(ext in link for ext in ignore_sites):
            found = False
            counter = counter + 1
            https_url = link.split('/url?q=')[1].split('&')[0]
            print(f'scrapping url - {https_url}')
            request_result = requests.get( https_url ) 
            soup = bs4.BeautifulSoup( request_result.content, "html5lib" ) 
            titles = soup.find_all('h1')
            subtitles = soup.find_all('h2')
            mini_titles = soup.find_all('h3')
            description = soup.find_all('p')
            tables = soup.find_all('table')
            
            sub_content = []
            for i in range(0, len(description)):
                if i < len(titles):
                    sub_content.append(f'<title>{titles[i].text}</title>')
                
                sub_content.append(f'<description>{description[i].text}</description>')
                
                if i < len(tables):
                    table_body = tables[i].find('tbody')
                    if table_body is not None:
                        rows = table_body.find_all('tr')
                        data = []
                        for row in rows:
                            th_cols = row.find_all('th')
                            if len(th_cols) > 0:
                                th_cols = [ele.text.strip().replace('\\', '') for ele in th_cols]
                                data.append([ele for ele in th_cols if ele])
                        
                            td_cols = row.find_all('td')
                            if len(td_cols) > 0:
                                td_cols = [ele.text.strip().replace('\\', '') for ele in td_cols]
                                data.append([ele for ele in td_cols if ele])
                        sub_content.append(f'<table>{data}</table>')
                        sub_content.append('   ')
                found=True

            if found:    
                template.append(''.join(sub_content))
        # Top 5 links
        if counter > 10:
            break
    return '  '.join(template)
    

print(google_search('covid-19 death toll in india'))