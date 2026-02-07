# Usa uma imagem leve do Python
FROM python:3.9-slim

# Instala o Chrome e dependências necessárias para rodar sem tela
RUN apt-get update && apt-get install -y \
    wget gnupg unzip curl \
    && wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list' \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copia seus arquivos e instala as bibliotecas
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py .

# Configurações para o Chrome não travar
ENV CHROME_BIN=/usr/bin/google-chrome
ENV PORT=5000

# Comando que inicia o robô automaticamente
CMD ["python", "-u", "testecomandos.py", "--modo-robo"]