# Usa uma imagem leve do Python
FROM python:3.9-slim

# 1. Atualiza e instala ferramentas básicas (Wget e Curl)
RUN apt-get update && apt-get install -y wget curl unzip gnupg

# 2. Baixa e instala o Chrome OFICIAL (Método .deb direto)
# Isso evita aquele erro de chave GPG e erro 127
RUN wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
RUN apt-get install -y ./google-chrome-stable_current_amd64.deb

# 3. Limpa os arquivos de instalação para economizar espaço
RUN rm google-chrome-stable_current_amd64.deb && apt-get clean

# Define a pasta de trabalho
WORKDIR /app

# Instala as bibliotecas do Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- AQUI ESTA O SEGREDO DO ARQUIVO NÃO ENCONTRADO ---
# Copia todos os arquivos da pasta para dentro do container
# Assim não importa se chama testecomandos.py ou main.py, ele copia tudo.
COPY . .

# Variáveis de ambiente
ENV CHROME_BIN=/usr/bin/google-chrome
ENV PORT=5000

# Comando para iniciar
CMD ["python", "-u", "main.py", "--modo-robo"]