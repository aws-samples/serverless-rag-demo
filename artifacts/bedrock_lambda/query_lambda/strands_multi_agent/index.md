# Multi-Agent Orchestration Made Simple

STRANDS[https://strandsagents.com/] is a powerful multi-agent orchestration opensource sdk. We've used the "Agents as Tools" architectural pattern wherein our Specialised agents are wrapped in as callable functions that can be used by other Agents. The Primary Orchestrator handles user interaction and calles relevant specialist agents. It then reflects if the user question is successfully answered 


## System Architecture

```mermaid
graph TB
    subgraph "User Interface"
        UI[WebSocket Client]
    end

    subgraph "STRANDS Multi-Agent System"
        Orchestrator[Orchestrator Agent]
        
        subgraph "Specialist Agents"
            WebSearch[Web Search Agent]
            Retriever[RAG Agent]
            CodeGen[Code Generator]
            Weather[Weather Agent]
            PPTGen[PPT Generator]
            General[General Assistant]
        end

        subgraph "Agent Tools"
            subgraph "Web Search Tools"
                DuckDuckGo[DuckDuckGo Search]
                Wikipedia[Wikipedia Scraper]
                YahooFinance[Yahoo Finance Scrapper]
                Summarizer[Summarizer]
            end

            subgraph "RAG Tools"
                QueryTranslation[Query Translation]
                QueryRewrite[Query Rewrite]
                FetchData[Fetch Data]
            end

            subgraph "Code Tools"
                UploadToS3[Upload To S3 ]
            end

            subgraph "Weather Tools"
                GetLatLong[Get Lat Long]
                GetWeather[Get Weather]
            end

            subgraph "PPT Tools"
                GeneratePPT[Generate Presentation]
            end

        end

        subgraph "External Services"
            Bedrock[Amazon Bedrock]
            OpenSearch[OpenSearch]
            S3[S3 Storage]
            WeatherAPI[OpenWeatherMap]
        end
    end

    UI -->|WebSocket| Orchestrator
    Orchestrator -->|Route Query| WebSearch
    Orchestrator -->|Route Query| Retriever
    Orchestrator -->|Route Query| CodeGen
    Orchestrator -->|Route Query| Weather
    Orchestrator -->|Route Query| PPTGen
    Orchestrator -->|Route Query| General

    WebSearch -->|Use| DuckDuckGo
    WebSearch -->|Use| Wikipedia
    WebSearch -->|Use| YahooFinance
    WebSearch -->|Use| Summarizer
    Retriever -->|Use| QueryTranslation
    Retriever -->|Use| QueryRewrite
    Retriever -->|Use| FetchData
    CodeGen -->|Use| UploadToS3
    Weather -->|Use| GetLatLong
    Weather -->|Use| GetWeather
    PPTGen -->|Use| GeneratePPT
    
    WebSearch -->|Search| Bedrock
    Retriever -->|Query| OpenSearch
    Retriever -->|Store| S3
    CodeGen -->|Generate| Bedrock
    Weather -->|Forecast| WeatherAPI
    PPTGen -->|Generate| Bedrock
    PPTGen -->|Store| S3
    General -->|Chat| Bedrock

    classDef agent fill:#f9f,stroke:#333,stroke-width:2px
    classDef tool fill:#ffd,stroke:#333,stroke-width:2px
    classDef service fill:#bbf,stroke:#333,stroke-width:2px
    classDef external fill:#bfb,stroke:#333,stroke-width:2px
    
    class WebSearch,Retriever,CodeGen,Weather,PPTGen,General agent
    class DuckDuckGo,Wikipedia,YahooFinance,Summarizer,QueryTranslation,QueryRewrite,FetchData,
    UploadToS3,GetLatLong,GetWeather,GeneratePPT tool
    class Orchestrator service
    class Bedrock,OpenSearch,S3,WeatherAPI external
```

## Installation

```bash
pip install strands-agents strands-agents-tools
```

* You can also run these agents individually in standalone mode