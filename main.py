import time
import os
import requests 
import sys
import psutil 
import gc
import re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from flask import Flask, request, jsonify
import threading
import queue

# ==============================================================================
# ⚙️ CONFIGURAÇÕES
# ==============================================================================
EVOLUTION_URL = "https://n8n-evolution-teste.laalxr.easypanel.host"
EVOLUTION_INSTANCE = "Evoteste"        
EVOLUTION_APIKEY = "DEV280@NEXT"

URL_LOGIN = "https://paineladmin3.azurewebsites.net/mobfy/login" 
URL_MAPA = "https://paineladmin3.azurewebsites.net/mobfy/vermapa"
URL_DASH = "https://paineladmin3.azurewebsites.net/mobfy/dashboard" # Ajuste se necessário

USUARIO_PAINEL = os.getenv("PAINEL_USER", "samuelluiz280@gmail.com") 
SENHA_PAINEL = os.getenv("PAINEL_PASS", "F@velado0")

ID_GRUPO_AVISOS = "120363421503531873@g.us"
ADMINS_TECNICOS = "120363407043661851@g.us" 
ADMIN_GERAL ="120363404153773063@g.us"
PERMISSAO_TOTAL = ["1713926848687", "5538999003357"] # Seus números e do outro dono (Restart)
PERMISSAO_BASICA = ["554977777777"] + PERMISSAO_TOTAL # Gerentes (Status/Reforço)
GRUPOS_PERMITIDOS = [
    ADMIN_GERAL,
    ADMINS_TECNICOS
]
# --- TEMPOS (EM MINUTOS) ---
TEMPO_OFFLINE = 3       
TEMPO_FROTA = 30        
TEMPO_CORRIDAS = 30     
TEMPO_HEARTBEAT = 40   

PORCENTAGEM_CRITICA_OCUPACAO = 60   
TEMPO_COOLDOWN_REFORCO = 30         
QTD_CRITICA_OFFLINE = 16            

# --- ESTADO GLOBAL ---
hora_inicio_bot = time.time()
ultimo_aviso_reforco = 0
estatisticas_dia = {'pico': 0, 'hora_pico': "", 'fechamento_enviado': False}
monitoramento_ativo = True  # <--- ADICIONE ISSO (Começa ligado)
fila_comandos = queue.Queue()
app = Flask(__name__)

# ==============================================================================
# 🛠️ FUNÇÕES AUXILIARES
# ==============================================================================
def limpeza_inicial_linux():
    # print("🧹 Limpeza global desativada para evitar conflito...")
    # try:
    #    os.system("pkill -f chrome")
    #    os.system("pkill -f chromedriver")
    # except: pass
    return # Não faz nada

def obter_uso_vps():
    try:
        mem = psutil.virtual_memory()
        return psutil.cpu_percent(interval=1), mem.percent, f"{mem.used/(1024**3):.1f}GB"
    except: return 0, 0, "?"

def enviar_msg(texto, destinatario=ID_GRUPO_AVISOS):
    print(f"📤 Enviando: {texto[:30]}...")
    url = f"{EVOLUTION_URL}/message/sendText/{EVOLUTION_INSTANCE}"
    payload = {"number": destinatario, "textMessage": {"text": texto}}
    try: requests.post(url, json=payload, headers={"apikey": EVOLUTION_APIKEY}, timeout=10)
    except: pass

def ler_texto(driver, xpath):
    """Função necessária para o Dashboard"""
    try:
        elemento = driver.find_element(By.XPATH, xpath)
        return elemento.text
    except:
        return "0"
    

def filtrar_dados_offline(texto_bruto):
    if not texto_bruto: return " Dados Carregando..."
    try:
        match_nome = re.search(r'Nome:\s*(.+)', texto_bruto)
        nome = match_nome.group(1).strip() if match_nome else "Motorista"
        
        match_cel = re.search(r'Celular:\s*([0-9\(\)\-\s]+)', texto_bruto, re.IGNORECASE)
        telefone = match_cel.group(1).strip() if match_cel else "Sem nº"

        return f"{nome} \n {telefone}"
    except: return f"Erro Leitura"   
# ==============================================================================
# 🛠️ MOTOR & LOGIN (MODO 1 ABA)
# ==============================================================================
def criar_driver():
    print("🤖 Iniciando Chrome (Modo VPS Linux)...")
    options = ChromeOptions()
    
    # --- OBRIGATÓRIOS PARA VPS ---
    options.add_argument("--headless=new")  # Roda sem abrir janela (essencial)
    options.add_argument("--no-sandbox")    # Necessário para rodar como root/docker
    options.add_argument("--disable-dev-shm-usage") # Evita crash por memória compartilhada
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    
    # Máscara para não parecer robô (Opcional mas recomendado)
    options.add_argument("user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    # Instala o driver compatível automaticamente
    servico = Service(ChromeDriverManager().install())
    
    return webdriver.Chrome(service=servico, options=options)

def garantir_login(driver):
    """Função de login ajustada para o campo 'usuário'"""
    if "login" in driver.current_url:
        print("Tela de login detectada")
        
        try:
            wait = WebDriverWait(driver, 15)
            
            # --- 1. PREENCHER USUÁRIO ---
            print("⏳ Procurando campo Usuário...")
            # Tenta encontrar por Placeholder ('usuário'), pelo Name ou pega o primeiro input de texto
            try:
                campo_user = wait.until(EC.element_to_be_clickable((By.XPATH, "//input[@placeholder='usuário' or @name='usuario' or @name='username' or @type='text']")))
            except:
                # Se falhar, tenta pegar o PRIMEIRO input da tela (força bruta)
                inputs = driver.find_elements(By.TAG_NAME, "input")
                campo_user = inputs[0] # O primeiro costuma ser o usuário
            
            campo_user.clear()
            campo_user.send_keys(USUARIO_PAINEL)
            
            # --- 2. PREENCHER SENHA ---
            # A senha é mais fácil, geralmente é o único type='password'
            campo_senha = driver.find_element(By.CSS_SELECTOR, "input[type='password']")
            campo_senha.clear()
            campo_senha.send_keys(SENHA_PAINEL)
            
            # --- 3. CLICAR NO BOTÃO ---
            print("Clicando em Login")
            try: 
                botao = driver.find_element(By.XPATH, "//button[contains(text(), 'Login') or .//span[contains(text(), 'Login')]]")
                botao.click()
            except:
                # Se não achar o botão, aperta ENTER no campo de senha
                from selenium.webdriver.common.keys import Keys
                campo_senha.send_keys(Keys.ENTER)
            
            # --- 4. CONFIRMAR SUCESSO ---
            # Espera a URL mudar (sair de 'login') ou aparecer o mapa
            WebDriverWait(driver, 20).until(lambda d: "login" not in d.current_url)
            print("✅ Login realizado com sucesso!")
            time.sleep(5) # Espera o painel carregar
            
        except Exception as e:
            print(f"⚠️ Falha no login: {e}")
            driver.save_screenshot("erro_login_novo.png")

def tarefa_offline_inteligente(driver):
    """
    Monitora pinos amarelos (Versão Corrigida com Iframe e Leitura Flexível)
    """
    print("\n🔍 [OFFLINE] Buscando pinos amarelos")
    
    # Variável para controlar se entramos no iframe
    entrou_no_iframe = False

    try:
        # 1. Garante que está na URL certa
        if "vermapa" not in driver.current_url:
            print("🔄 URL incorreta. Indo para mapa...")
            driver.get(URL_MAPA)
            time.sleep(8)
        else:
            driver.refresh()
            time.sleep(8)

        # ==================================================================
        # 2. CORREÇÃO CRÍTICA: ENTRAR NO IFRAME DO MAPA
        # ==================================================================
        try:
            iframe = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "iframe[src*='google'], iframe[id*='map']"))
            )
            driver.switch_to.frame(iframe)
            entrou_no_iframe = True # Marca que entramos para sair depois
        except:
            print("⚠️ Iframe do mapa não encontrado (tentando buscar direto...)")

        # Espera os pinos carregarem
        try:
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "img[src*='pin-']")))
        except: pass

        amarelos = driver.find_elements(By.CSS_SELECTOR, "img[src*='pin-amarelo.png']")
        qtd_offline = len(amarelos)
        
        # CASO 0: Tudo limpo
        if qtd_offline == 0:
            print("✅ [OFFLINE] Rede estável.")
            if entrou_no_iframe: driver.switch_to.default_content()
            return

        # CASO CRÍTICO: Queda massiva
        if qtd_offline >= QTD_CRITICA_OFFLINE:
            print(f"⚠️ [CRÍTICO] {qtd_offline} offlines!")
            if entrou_no_iframe: driver.switch_to.default_content()
            
            mensagem = (
                f"🚨 *ALERTA CRÍTICO: INSTABILIDADE NA REDE* 🚨\n\n"
                f"⚠️ *{qtd_offline} motoristas offline* simultaneamente.\n"
                f"📢 *AÇÃO:* Reiniciar celulares."
            )
            enviar_msg(mensagem, ID_GRUPO_AVISOS)
            return

        # CASO PADRÃO: Ler Motoristas
        print(f"⚠️ [OFFLINE] {qtd_offline} detectados. Lendo dados...")
        lista_final = []

        for i, pino in enumerate(amarelos[:15]): 
            try:
                # Clica no pino via Javascript (mais seguro dentro do mapa)
                driver.execute_script("arguments[0].click();", pino)
                time.sleep(1.5) 
                
                try:
                    # Tenta ler o balão
                    balao = driver.find_element(By.CLASS_NAME, "gm-style-iw")
                    texto_bruto = balao.text
                    
                    # --- LÓGICA DE EXTRAÇÃO MELHORADA ---
                    # Se a regex padrão falhar, tenta pegar "na força bruta"
                    infos = filtrar_dados_offline(texto_bruto)
                    
                    if "Erro Leitura" in infos:
                        # Plano B: Pega a primeira linha como nome e busca telefone no texto todo
                        linhas = texto_bruto.split('\n')
                        nome_b = linhas[0].strip() if linhas else "Motorista"
                        match_cel = re.search(r'([0-9]{2}\s*9?[0-9]{4}[-\s]?[0-9]{4})', texto_bruto)
                        tel_b = match_cel.group(1) if match_cel else "Sem nº"
                        infos = f" {nome_b} \n {tel_b}"

                    lista_final.append(infos)
                    print(f"   -> Lido: {infos.splitlines()[0]}")
                    
                except:
                    lista_final.append(" Erro ao ler balão")
                
                # Fecha o balão
                try:
                    driver.find_element(By.CLASS_NAME, "gm-ui-hover-effect").click()
                except:
                    # Clica num ponto vazio do mapa se não achar o X
                    driver.find_element(By.TAG_NAME, 'body').click()
                
                time.sleep(0.5)
            except: continue

        # Sai do Iframe antes de enviar a mensagem
        if entrou_no_iframe: driver.switch_to.default_content()

        if lista_final:
            texto_zap = "\n".join(lista_final)
            mensagem = (
                f"⚠️ *ALERTA: MOTORISTAS OFFLINE - {time.strftime('%H:%M')}*\n"
                f"📡 Total: {qtd_offline}\n\n"
                f"{texto_zap}"
            )
            enviar_msg(mensagem, ID_GRUPO_AVISOS)

    except Exception as e:
        print(f"❌ Erro Tarefa Offline: {e}")
        # Importante sair do iframe se der erro, senão o próximo loop trava
        try: driver.switch_to.default_content()
        except: pass
    
# ==============================================================================
# 🗺️ TAREFAS (SEQUENCIAIS)
# ==============================================================================

def tarefa_mapa_geral(driver):
    global ultimo_aviso_reforco
    print("\n🗺️ [MAPA] Verificando...")
    
    if "login" in driver.current_url: garantir_login(driver)

    # CORREÇÃO AQUI: Removemos a função de trocar aba que não existia
    if "vermapa" not in driver.current_url:
        driver.get(URL_MAPA)
        time.sleep(10)
    else:
        # Se já estiver no mapa, dá um refresh para atualizar os pinos
        driver.refresh()
        time.sleep(8)
    
    # Entra no iframe
    try:
        iframe = WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, "iframe[src*='google'], iframe[id*='map']")))
        driver.switch_to.frame(iframe)
    except: pass 

    # Espera pinos
    try: WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "img[src*='pin-']")))
    except: pass

    # Contagem
    html = driver.execute_script("return document.documentElement.outerHTML;")
    livres = html.count("pin-verde")
    ocupados = html.count("pin-vermelho")
    offline = html.count("pin-amarelo")
    total = livres + ocupados
    
    driver.switch_to.default_content()
    print(f"🏁 Status: 🟢{livres} 🔴{ocupados} 🟡{offline}")

    if total > 0:
        porc = round((ocupados / total) * 100)
        situacao = "🟢" if porc < 40 else "🟡" if porc < 75 else "🔴 ALTA"
        
        msg = (
            f"📊 *STATUS DA FROTA | {time.strftime('%H:%M')}*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{situacao} - {porc}% ocupado\n\n"
            f"🟢 Livres: {livres}\n"
            f"🔴 Ocupados: {ocupados}\n"
            f"🚗 Total: {total}\n"
            f"━━━━━━━━━━━━━━━━━━"
        )
        enviar_msg(msg, ID_GRUPO_AVISOS)
        
        agora = time.time()
        if (porc >= PORCENTAGEM_CRITICA_OCUPACAO) and ((agora - ultimo_aviso_reforco)/60 >= TEMPO_COOLDOWN_REFORCO):
            enviar_msg(f"⚠️ *REFORÇO NECESSÁRIO:* Demanda {porc}%.", ID_GRUPO_AVISOS)
            ultimo_aviso_reforco = agora

    if offline >= QTD_CRITICA_OFFLINE:
         enviar_msg(f"🚨 *ALERTA:* {offline} motoristas offline!", ID_GRUPO_AVISOS)

def tarefa_dashboard(driver, destinatario=None):
    print("\n📈 [DASHBOARD] Lendo...")
    
    if "login" in driver.current_url: garantir_login(driver)
    
    # Se não estiver no dash, vai pra lá
    if "dashboard" not in driver.current_url:
        try:
            driver.get(URL_DASH)
            time.sleep(5)
        except: return

    try:
        xp_sol = '/html/body/div/app/div/div/div[2]/div[2]/div/div[1]/h3'
        xp_con = '/html/body/div/app/div/div/div[2]/div[3]/div/div[1]/h3'
        
        txt_sol = ler_texto(driver, xp_sol)
        txt_con = ler_texto(driver, xp_con)
        
        sol = int(txt_sol.replace('.','')) if txt_sol else 0
        con = int(txt_con.replace('.','')) if txt_con else 0
        perdidas = sol - con
        conversao = round((con / sol) * 100) if sol > 0 else 0
        
        msg = (
            f"📈 *Relatório de Desempenho - {time.strftime('%H:%M')}*\n"
            f"📥 Solicitações: {txt_sol}\n✅ Finalizadas: {txt_con}\n"
            f"🚫 Perdidas: {perdidas}\n📊 Conversão: {conversao}%"
        )
        
        # Lógica: Se alguém pediu, manda pra ele. Se for automático, manda pro Admin Geral.
        quem_recebe = destinatario if destinatario else ADMIN_GERAL
        enviar_msg(msg, quem_recebe)
        
        print(f"✅ Dashboard Lido: {conversao}%")
            
    except Exception as e:
        print(f"⚠️ Erro dashboard: {e}")

def tarefa_offline_inteligente(driver):
    """
    Monitora pinos amarelos 
    """
    print("\n🔍 [OFFLINE] Buscando pinos amarelos")
    try:
        
        # Lógica de Reset e Segurança da URL
        if "vermapa" not in driver.current_url:
            print("🔄 URL incorreta na Aba 2. Forçando mapa...")
            driver.get(URL_MAPA)
            time.sleep(8)
        else:
            # Refresh OBRIGATÓRIO para limpar filtros da tarefa de Frota anterior
            driver.refresh()
            time.sleep(10) # Tempo vital para carregar o mapa

        amarelos = driver.find_elements(By.CSS_SELECTOR, "img[src*='pin-amarelo.png']")
        qtd_offline = len(amarelos)
        
        # CASO 0: Tudo limpo
        if qtd_offline == 0:
            print("✅ [OFFLINE] Rede estável.")
            return

        # CASO CRÍTICO: Queda de rede
        if qtd_offline >= QTD_CRITICA_OFFLINE:
            print(f"⚠️ [CRÍTICO] {qtd_offline} offlines!")
            mensagem = (
                f"🚨 *ALERTA CRÍTICO: INSTABILIDADE NA REDE* 🚨\n\n"
                f"⚠️ *{qtd_offline} motoristas offline* simultaneamente.\n\n"
                f"📢 *AÇÃO:* Provável falha de operadora. Reiniciem os celulares."
            )
            enviar_msg(mensagem, ID_GRUPO_AVISOS)
            return

        # CASO PADRÃO: Lista individual
        print(f"⚠️ [OFFLINE] {qtd_offline} detectados. Lendo dados...")
        lista_final = []

        for i, pino in enumerate(amarelos[:15]): # Limite 15 para não demorar
            try:
                # Clica no pino
                driver.execute_script("arguments[0].click();", pino)
                time.sleep(1.5) # Espera o balão abrir
                
                try:
                    # CORREÇÃO 2: Pega o balão pela Classe (Mais estável que XPath)
                    balao = driver.find_element(By.CLASS_NAME, "gm-style-iw")
                    texto = balao.text
                    
                    # Usa a função blindada v4.0
                    info_formatada = filtrar_dados_offline(texto)
                    lista_final.append(info_formatada)
                    
                    print(f"   -> Lido: {info_formatada.replace(chr(10), ' ')}") # Printa em 1 linha
                    
                except:
                    # Se não abriu o balão ou deu erro
                    lista_final.append("🚫 Erro ao ler balão")
                
                # Fecha o balão clicando no botão X ou no corpo
                try:
                    fechar = driver.find_element(By.CLASS_NAME, "gm-ui-hover-effect")
                    fechar.click()
                except:
                    driver.find_element(By.TAG_NAME, 'body').click()
                
                time.sleep(0.5)
            except: continue

        if lista_final:
            texto_zap = "\n".join(lista_final)
            mensagem = (
                f"⚠️ *ALERTA: MOTORISTAS OFFLINE - {time.strftime('%H:%M')}*\n"
                f"📡 Total Sem Sinal: {qtd_offline}\n\n"
                f"{texto_zap}"
            )
            enviar_msg(mensagem, ID_GRUPO_AVISOS)

    except Exception as e:
        print(f"❌ Erro Tarefa Offline: {e}")

def tarefa_heartbeat(destinatario=None):
    # MUDANÇA AQUI: Se for automático, manda pro ADMINS_TECNICOS (Você)
    quem_recebe = destinatario if destinatario else ADMINS_TECNICOS
    
    uptime = round((time.time() - hora_inicio_bot) / 3600, 1)
    cpu, ram_porc, ram_info = obter_uso_vps()
    
    status_ram = "🟢" if ram_porc < 85 else "⚠️"
    msg = (f"🤖 *Monitor Técnico* {status_ram}\n⏱️ Up: {uptime}h\n🧠 CPU: {cpu}%\n💾 RAM: {ram_porc}% ({ram_info})")
    
    enviar_msg(msg, quem_recebe)
    
def tarefa_reiniciar_bot(driver, motivo):
    print(f"🔄 [RESTART] Reiniciando: {motivo}")
    
    # 1. Tenta avisar e fechar o navegador
    try:
        # Mudei o texto aqui para (1h)
        msg = f"♻️ *REINÍCIO *\nMotivo: {motivo}"
        enviar_msg(msg, ADMINS_TECNICOS)
        
        if driver:
            driver.quit()
    except: 
        print("⚠️ Erro ao fechar driver no restart.")
    
    time.sleep(2)
    
    # 2. COMANDO DE REINÍCIO AUTOMÁTICO (Ressuscita o Robô)
    print("🚀 Recarregando script...")
    python = sys.executable
    sys.exit(0)
    
# ==============================================================================
# FUNÇÃO WEBHOOK
# ==============================================================================
@app.route('/webhook', methods=['POST'])
def receber_mensagem():
    try:
        body = request.json
        if body.get('event') == 'messages.upsert':
            msg_data = body.get('data', {})
            key = msg_data.get('key', {})
            remote_jid = key.get('remoteJid', '')
            participant = key.get('participant', remote_jid)
            
            mensagem = ""
            if 'conversation' in msg_data.get('message', {}):
                mensagem = msg_data['message']['conversation']
            elif 'extendedTextMessage' in msg_data.get('message', {}):
                mensagem = msg_data['message']['extendedTextMessage'].get('text', '')
            mensagem = mensagem.strip().lower()

            # --- ⛔ PORTEIRO: BLINDAGEM TOTAL ⛔ ---
            # Se a mensagem NÃO veio de um dos dois grupos oficiais, O ROBÔ IGNORA.
            # Não manda mensagem, não printa, não faz nada. Morre aqui.
            if remote_jid not in GRUPOS_PERMITIDOS:
                return jsonify({"status": "ignorado"}), 200

            # Se passou daqui, é porque está num grupo oficial.
            # Vamos ver se é comando:
            if mensagem.startswith("/"):
                # Identifica quem mandou (só para log interno se precisar)
                quem_mandou = participant.split('@')[0] if participant else ""
                print(f"👀 Comando '{mensagem}' | De: {quem_mandou} | Em: {remote_jid}")
            else:
                return jsonify({"status": "texto comum"}), 200

            # --- DEFINIÇÃO DO LOCAL ---
            eh_grupo_cliente = (remote_jid == ADMIN_GERAL)
            eh_grupo_tecnico = (remote_jid == ADMINS_TECNICOS)

            # --- 1. COMANDOS OPERACIONAIS (Funcionam nos 2 grupos) ---
            if mensagem == "/ajuda":
                msg_ajuda = (
                    "🤖 *CENTRAL DE COMANDOS*\n"
                    "━━━━━━━━━━━━━━━━\n"
                    "📌 *Operacional:*\n"
                    "*/status* - Ver mapa e motoristas\n"
                    "*/relatorio* - Ver números do painel\n"
                    "*/reforco* - Enviar alerta de demanda\n"
                    "*/pausar* - Parar envio automático\n"
                    "*/voltar* - Retomar envio automático"
                )
                enviar_msg(msg_ajuda, remote_jid)

            elif mensagem == "/status":
                enviar_msg("🫡 Gerando status...", remote_jid)
                fila_comandos.put(("CMD_STATUS", remote_jid))

            elif mensagem == "/reforco":
                enviar_msg("🫡 Disparando alerta!", remote_jid)
                fila_comandos.put(("CMD_REFORCO", remote_jid))
            
            elif mensagem == "/relatorio":
                enviar_msg("📊 Lendo dashboard...", remote_jid)
                fila_comandos.put(("CMD_RELATORIO", remote_jid))

            elif mensagem == "/pausar":
                enviar_msg("⏸️ Pausando bot...", remote_jid)
                fila_comandos.put(("CMD_PAUSAR", remote_jid))

            elif mensagem == "/voltar":
                enviar_msg("▶️ Retomando bot...", remote_jid)
                fila_comandos.put(("CMD_VOLTAR", remote_jid))

            # --- 2. COMANDOS TÉCNICOS (Só funcionam no ADMINS_TECNICOS) ---
            # Se tentarem usar isso no grupo do cliente, o robô TAMBÉM IGNORA (Segurança)
            
            elif mensagem == "/bot" and eh_grupo_tecnico:
                enviar_msg("Verificando...", remote_jid)
                fila_comandos.put(("CMD_HEALTH", remote_jid)) 

            elif mensagem == "/reiniciar" and eh_grupo_tecnico:  
                enviar_msg("Reiniciando...", remote_jid)
                fila_comandos.put(("CMD_REINICIAR", remote_jid))

    except Exception as e: print(f"Erro Webhook: {e}")
    return jsonify({"status": "ok"}), 200

def rodar_servidor():
    # O Easypanel define a porta na variável de ambiente PORT
    port_number = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port_number, use_reloader=False)
 
# ==============================================================================
# 🚀 LOOP PRINCIPAL
# ==============================================================================
if __name__ == "__main__":
# --- PARTE 1: O GERENTE (MONITOR) ---
    # Se rodar normal, entra aqui. Ele fica vigiando.
    if "--modo-robo" not in sys.argv:
        import subprocess
        print("Iniciando...")
        
        while True:
            try:
                # O Gerente chama este mesmo arquivo, mas adicionando a senha "--modo-robo"
                # Isso cria um processo filho (limpo de memória e porta)
                print(f" Iniciando processos ({time.strftime('%H:%M:%S')})")
                
                # Usa o mesmo Python que você usou para rodar o script (venv)
                p = subprocess.Popen([sys.executable, sys.argv[0], "--modo-robo"])
                
                p.wait() # O Gerente fica parado aqui esperando o Robô fechar/cair
                
            except KeyboardInterrupt:
                print("\n🛑 Monitor interrompido pelo usuário.")
                sys.exit(0)
            except Exception as e:
                print(f"❌ Erro no Monitor: {e}")
            
            print(" O robô encerrou. Reiniciando em 5 segundos...")
            time.sleep(5) # Tempo para liberar a porta 5000
            # O loop volta e abre o robô de novo

    # --- PARTE 2: O ROBÔ (TRABALHADOR) ---
    # Só entra aqui se tiver a flag "--modo-robo" (quem chama é o Gerente acima)
    else:
        limpeza_inicial_linux()
    
    try:
        # matar a porta 5000 caso esteja em uso
        os.system("fuser -k 5000/tcp > /dev/null 2>&1") 
    except: pass
    time.sleep(3)
    
    try:
        # --- 1. INICIALIZAÇÃO DO DRIVER ---
        driver = criar_driver()
        driver.get(URL_LOGIN) 
        garantir_login(driver)
        
        # --- 2. INICIALIZAÇÃO DO SERVIDOR DE COMANDOS (Faltava isso!) ---
        # Isso cria uma "pista paralela" para o Flask rodar sem travar o robô
        t_server = threading.Thread(target=rodar_servidor)
        t_server.daemon = True # Se o robô fechar, o server fecha junto
        t_server.start()
        print(" Webhook de comandos ativo")

        # --- 3. DEFINIÇÃO DE TEMPOS ---
        agora = time.time()
        t_off = agora + 10
        t_mapa = agora + 5
        t_dash = agora + 60
        t_heart = agora + 10
        t_restart = agora + (1 * 3600) # Reinicia a cada 1h

        enviar_msg("🚀 *Robô Iniciado*", ADMINS_TECNICOS)

        # --- 4. LOOP PRINCIPAL ---
        while True:
                agora = time.time()

                # --- 1. PROCESSAMENTO DE COMANDOS (Prioridade Total) ---
                if not fila_comandos.empty():
                    try:
                        comando, origem_pedido = fila_comandos.get() 
                        print(f"⚙️ Executando: {comando}")
                        
                        if comando == "CMD_STATUS":
                            enviar_msg("✅ Enviando mapa...", origem_pedido)
                            tarefa_mapa_geral(driver) # Manda no grupo padrão mas avisa quem pediu
                        
                        elif comando == "CMD_RELATORIO":
                            # Chama a nova versão do dashboard passando quem pediu
                            tarefa_dashboard(driver, destinatario=origem_pedido)

                        elif comando == "CMD_REFORCO":
                            msg = "🚨 *ALERTA*\n\n⚠️ *ALTA DEMANDA*\n📢 Motoristas: Fiquem Online!"
                            enviar_msg(msg, ID_GRUPO_AVISOS)
                            enviar_msg("✅ Alerta enviado.", origem_pedido)
                        
                        elif comando == "CMD_PAUSAR":
                            monitoramento_ativo = False
                            print("⏸️ Bot Pausado via WhatsApp")
                        
                        elif comando == "CMD_VOLTAR":
                            monitoramento_ativo = True
                            print("▶️ Bot Retomado via WhatsApp")
                            # Reseta os timers para verificar logo
                            t_off = t_mapa = t_dash = agora + 5 

                        elif comando == "CMD_REINICIAR":
                            tarefa_reiniciar_bot(driver, "Comando via WhatsApp")
                        
                        elif comando == "CMD_HEALTH":
                            # Executa a função de heartbeat respondendo pra quem pediu
                            tarefa_heartbeat(destinatario = origem_pedido)
                            
                        elif comando == "CMD_AJUDA":
                            msg_ajuda = (
                                "🤖 *CENTRAL DE COMANDOS*\n"
                                "━━━━━━━━━━━━━━━━\n"
                                "📌 *Operacional:*\n"
                                "*/status* - Status da Frota\n"
                                "*/relatorio* - Relatório de Motoristas\n"
                                "*/reforco* - Alerta de pico\n\n"
                                "📌 *Controle do Robô:*\n"
                                "*/pausar* - Parar Bot\n"
                                "*/voltar* - Retomar Bot"
                            )
                            enviar_msg(msg_ajuda, origem_pedido)
                            
                    except Exception as e:
                        print(f"⚠️ Erro comando: {e}")

                if monitoramento_ativo:
                    
                    if agora >= t_off: 
                        tarefa_offline_inteligente(driver); t_off = agora + (TEMPO_OFFLINE * 60)

                    if agora >= t_mapa:
                        tarefa_mapa_geral(driver)
                        t_mapa = agora + (TEMPO_FROTA * 60)
                    
                    if agora >= t_dash:
                        tarefa_dashboard(driver)
                        t_dash = agora + (TEMPO_FROTA * 60)
                
                else:
                    pass

                if agora >= t_heart:
                    tarefa_heartbeat()
                    t_heart = agora + (TEMPO_HEARTBEAT * 60)
                    gc.collect()

                if agora >= t_restart:
                    tarefa_reiniciar_bot(driver, "Reinício Programado")

                time.sleep(5)

    except Exception as e:
        print(f"❌ Erro Fatal no Loop: {e}")
        time.sleep(5)
        os.execl(sys.executable, sys.executable, *sys.argv)