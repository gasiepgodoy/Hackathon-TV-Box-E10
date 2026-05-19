# 💡│ Introdução
Como todos sabem, as famosas TVs Boxes são dispositivos considerados ilegais pelo conteúdo que os mesmos possuem, porém elas por si só, são hardwares que podem ser explorados de maneira legal, esse é o grande foco da competição.
Descaracterizar nada mais é do que, atribuir uma nova função à determinado equipamento, excluindo a sua utilidade primordial, ou seja, no nosso caso retiráramos a pirataria para implementarmos uma nova aplicação, afinal é uma tecnologia que pode ser útil.

**Esses aparelhos quando vistos de forma individual, não são ilegais, o “ilegal” está relacionado aos aplicativos instalados previamente, e de que maneira são utilizados.**

## 🧠 │ Lógica da Descaracterização
A teoria por trás é simples. Quando trabalhamos com esses equipamentos, no geral, pensamos da seguinte forma:
1. Buscamos uma imagem (geralmente derivada do Linux) para transformá-las em microcomputadores, assim muitas vezes desempenhando o mesmo papel que um raspberry pi em projetos, por exemplo.
2. Armazenamos/instalamos essa imagem, geralmente em pen-drive ou cartão microsd, para “bootar” na Box.
3. Para que esse processo de “boot” funcione, além de injetar e realizar o “update”, precisamos “ensinar” duas coisas ao dispositivo: 1. com qual o hardware estamos lidando, ou simplesmente, qual o modelo da TV Box que queremos descaracterizar, e nesse quesito entra o que chamamos de arquivo “Device Tree Blob (DTB)”, basicamente é um arquivo binário que descreve o hardware do dispositivo, permitindo ao sistema operacional reconhecer, e configurar todos os componentes do sistema, como processador, memória, portas USB, antena Wi-Fi entre outros, 2. da onde ele precisa retirar as informações presentes na imagem, para isso existe o “UUID”, uma espécie de endereço para acessar o seu pen-drive ou catão de memória, no qual você “diz” o caminho onde encontrá-lo.

**Obs:** Para configurações como o UUID e arquivo DTB necessário, acessamos os arquivos de configuração na pasta principal (o nome varia entre imagens, por exemplo: armbianEnv.txt, boot.config…), entretanto depende da imagem utilizada, em nossa recomendação a configuração do UUID não é necessária.

4. E para finalizar, carregamos a nova imagem no aparelho e realizamos o login.

# 🔴🐧 │ Debian 13
A imagem que recomendamos se trata de um sistema derivado do Linux em uma versão server, ou seja, a manipulação e uso parte apenas de comandos, não possuindo uma interface gráfica como o Windows que conhecemos.

**Escolhemos a seguinte imagem por conta de ser bem otimizada, fácil instalação, exigir poucos passos de configuração até que esteja pronta para uso, e por fim, compatibilidade com a placa Wi-Fi da TV Box possibilitando conexão pela rede sem fio.**

## 📦 │ Instalação
A seguir iremos detalhar os passos a serem seguidos:
- **Primeiro passo:** Faça o download do arquivo em [Imagens Recomendadas](Imagens%20pra%20uso/)
- **Segundo passo:** Instale o programa chamado Balena Etcher ou outro software semelhante para gravar a imagem dentro do pen-drive ou cartão de memória.
**Link para o Balena Etcher:** https://etcher.balena.io/
- **Terceiro passo:** Após a gravação, retire e plugue-o novamente no Pc para evitar possíveis erros e em seguida abra o disco e acesse a partição principal criada, dentro dela abra o arquivo “boot.config” com o bloco de notas para poder modificá-lo e descomente a linha de configuração referente ao hardware da sua btv (em nosso caso: “box-s905x2_generic”), para isso remova a “#”.
- **Quarto passo:** Depois de configurar, pegue o pen-drive e encaixe na entrada USB 2.0 do dispositivo, ou conecte o cartão de memória na entrada para cartão microsd se for o caso. Se a TV Box já estava ligada na tomada pressione o botão de reset e na sequência mantenha pressionado o botão de update durante alguns segundos até começar a inicialização, e se a TV Box estiver desligada, conecte-a e apenas segure o botão de update no mesmo momento.
**Obs:** Por via de regra, para garantir q n aconteça nenhum problema, aperte uma vez o botão de reset em ambos os casos.
- **Quinto passo:** Aguarde a inicialização da imagem e quando encerrar realize o login pelo usuário e senha “root” e “tvbox”, respectivamente como mostrado na interface inicial. 

**Parabéns, agora você possui um dispositivo rodando um sistema derivado do Linux.**

## ⚙️ │ Configuração
Nesta seção iremos explicitar alguns comandos úteis e configurações iniciais básicas.

Depois de iniciado, caso o dispositivo esteja conectado a rede, já é possível observar o ip ao qual a máquina foi cadastrada (isso se utilizarem a rede da universidade), ou em redes privadas, geralmente o número é gerado de forma aleatória. Após o localizarem, podemos acessar a Box via “SSH”, proporcionando que acessemos a mesma a partir de outro computador ou até mesmo de celulares e tablets, algo que facilita muito o manuseio desse aparelho, tendo em vista que nem sempre temos um monitor para visualizarmos ou teclado e mouse disponíveis.
**Ferramenta utilizada:** putty.

**Como acessar via putty:**

- **Primeiro passo:** Instale o software no dispositivo que deseja usar para acessar a Box remotamente.
**No Pc em um sistema Windows recomendamos instalar pela Microsoft Store:** https://apps.microsoft.com/detail/xpfnzksklbp7rj?hl=pt-BR&gl=BR
**Link opcional direto para o site do desenvolvedor:** https://www.putty.org/
**Obs:** Se desejar, pode utilizar outros softwares semelhantes, principalmente se não estiver em um Pc, em dispositivos móveis recomendamos o “Termius”.
- **Segundo passo:** Abra o aplicativo e logo de cara aparece já é selecionado o campo que deve ser preenchido, com o nome: “Host Name (or IP address)”, apenas escreva o endereço de IP que apareceu em sua btv, marque o SSH em “Connection Type” caso não tenha vindo marcado, e pressione Enter ou o botão “Open” abaixo para iniciar a conexão remota. 
**Obs:** Para evitar erros tendo em vista que todas as TV Boxes recebem o mesmo Host Name quando carregamos essa imagem, é preferível utilizar sempre o endereço de IP, sendo mais seguro e exato.
- **Terceiro passo:** Faça o login novamente com o usuário e senha, e pronto, conectado remotamente.

Para começarmos, uma boa prática é trocar a senha que vem por padrão, embora seja opcional a troca é simples apenas utilizando o seguinte comando:
- **“passwd <usuário>”** - Escreva o nome de usuário do qual você deseja alterar a senha (no caso de não ter alterado: root), e na sequência digite a nova senha.

Outro ponto importante é que, o sistema muitas vezes pode precisar de algumas atualizações ou instalação de alguns pacotes adicionais, portanto recomendamos que rode a lista de comandos a seguir:
- **“apt update”** - para verificar novas atualizações.
- **“apt upgrade”** - para atualizar os recursos já instalados.

**Aviso:** Caso apareça, ao final do “update” ou “upgrade”, uma nova interface perguntando: “What do you want to do about modified configuration file sshd_config?”, selecione a opção padrão “keep the local version currently installed” que geralmente já vem selecionada e aperte Enter.

**Pronto, agora seu sistema está pronto para seus futuros projetos.**

## ⚡📶 │ Comandos Atualização Wi-Fi Btv E10:
Nesse momento é muito comum que tenham problemas relacionados ao Wi-Fi e drivers de rede utilizando essa imagem, para resolvê-los recomendamos que sigam os passos e listas de comandos presentes abaixo:

**Obs:** O uso da imagem Debian Linux for Amlogic SOC já possui acesso root e os comandos não precisam usar o "sudo" no inicío.

**1) Atualizando e instalando pacotes:**

Atualizar pacotes:

- **"apt update && apt upgrade"** - Já vistos anteriormente, servem para atualizar pacotes.

Instalar pacotes básicos necessários:

- **"apt install build-essential git curl"**
- **"apt install dkms"**
- **"apt install usbutils"**
- **"apt install bc"**
- **"apt install wget"**
- **"apt install network-manager"**
- **"apt install pciutils"**
- **"apt install lshw"**
- **"apt install wireless-tools"**

Instalar driver realtek da placa wifi:

- **"apt install firmware-realtek"**

Verificar interfaces de rede disponíveis na box. Deve listar uma cabeada "eth0" e um sem fio "wlan0". Se tiver com o adaptador USB-WiFi reconhecido pode haver uma "wlan1":

- **"ip a"**

Escaneia redes wifi e imprimi lista com informações:

- **"nmcli dev wifi rescan"**

Verifique se sua rede wifi se encontra na lista:

- **"nmcli dev wifi list"**

Opções para conexão:

**"nmcli dev wifi connect <SSID> password <password>"** - Conectar de rede "SSID" com a senha "password". Troque pela credencial da sua rede wifi.

Ou:

Rodar o script "wifi-connect.sh" na pasta raiz da Tv Box. Ele vai perguntar qual rede wifi (SSID) vc quer conectar e qual a senha. Ele irá salvar essa conexão (SSID e senha) para futuras conexões.

Verifique em wlan0 se conectou na rede e recebeu algum endereço IP:

- **"ip a"**

Se a conexão do módulo Wi-Fi interno da Tv Box com o driver usado estiver muito ruim, recomenda-se procurar outro driver ou usar um adaptador USB-WiFi.

**2) Verificação do pacote linux-headers:**

apt-get install build-essential git dkms linux-headers-$(uname -r)

Se tiver o erro: "unable to locate package linux-readers":
Verifique a versão exata do seu kernel:

- **"uname -r"**

**"apt search linux-headers-"** - Seguido pelo número da versão geral para ver todos os pacotes disponíveis em seus repositórios. Ex: "apt search linux-headers-6.18.29".

Se não tiver o pacote do header do seu Kernel no seu repositório, será necessário adicioná-lo manualmente:
Localize o arquivo .deb correto para sua arquitetura (provavelmente arm64) na página de lançamentos do GitHub.

- **"https://github.com/devmfc/debian-on-amlogic/releases"** - Ex: "https://github.com/devmfc/debian-on-amlogic/releases/tag/v6.18.29".

Faça o download usando o wget:

- **"wget <URL_do_arquivo_deb>"** - Ex: "wget https://github.com/devmfc/debian-on-amlogic/releases/download/v6.18.29/linux-headers-6.18.29-meson64_20260511_arm64.deb"

Instale o pacote:

- **"dpkg -i <nome_do_pacote_baixado>.deb"** - O nome do pacote que for entregue após terminar a busca e instalação pelo wget. Ex: "dpkg -i linux-headers-6.18.29-meson64_20260511_arm64.deb"

- **"sudo apt install -f**" - "Corrigir possíveis dependências"

**3) Recomendado - Desabilitar WiFi Interno da TV Box para uso de Adaptador USB-WiFi:**

Cria um arquivo de configuração para desabilitar o módulo WiFi Interno:

- **"nano /etc/modprobe.d/disable-wifi-interno.conf"**

Liste o módulo para desabilitar:

- **"blacklist 8189fs"**

Reiniciar tv box:

- **"reboot"**

Checar conexões de rede:

- **"ip a"**

Somente deve ter uma conexão "wlan0" que corresponderá à interfave USB-WiFi conectada

**4) Instalação Driver USB Wifi "n" com Antena externa (se necessário):**

- **"https://github.com/kelebek333/rtl8188fu"**

**5) Instalação Driver USB Wifi "AC" Dual Band (se necessário):**

- **"https://www.youtube.com/watch?v=PGKRPWMglCs"**
- **"https://github.com/bitcris/RealtekRTL8811CU"**

Verifique se existe algum driver instaldo com o comando:

- **"dkms status"**

Se tiver, substitua pelo driver que aparece no seu terminal:
Verifique o ID do driver:

- **"lsusb"**
Exemplo de saída esperada: (Bus 001 Device 002: ID 0bda:c811 Realtek Semiconductor Corp. 802.11ac NIC)

Pacotes necessários:

- **"apt install -y build-essential dkms git iw"**

Cria o diretório para armazenar o driver e navega até o diretório:

- **"mkdir -p ~/src ; cd src"**

Baixa o driver:

- **"git clone https://github.com/morrownr/8821cu-20210916.git"**

Abre o diretório do driver:

- **"cd ~/src/8821cu-20210916"**

**ATENÇÃO:** Este script vai solicitar reiniar o computador.
Executa o script de instalação, você pode pular a reinicialização, mas recomenda-se reiniar

- **"./install-driver.sh"**

Reiniciar tv box:

- **"reboot"**

**6) Conectar na rede Wi-Fi:**

Verificar interfaces de rede disponíveis na box. Deve listar uma cabeada "eth0" e um sem fio "wlan0". Se tiver com o adaptador USB-WiFi reconhecido pode haver uma "wlan1":

- **"ip a"**

Escaneia redes wifi e imprimi lista com informações:

- **"nmcli dev wifi rescan"**

Verifique se sua rede wifi se encontra na lista:

- **"nmcli dev wifi list"**

Opções para conexão:

- **"nmcli dev wifi connect <SSID> password <password>"** - Conectar de rede "SSID" com a senha "password". Troque pela credencial da sua rede wifi.

Ou:

Rodar o script "wifi-connect.sh" na pasta raiz da Tv Box. Ele vai perguntar qual rede wifi (SSID) vc quer conectar e qual a senha. Ele irá salvar essa conexão (SSID e senha) para futuras conexões.

## 💻 │ Comandos úteis:
Para que ninguém fique totalmente perdido nesse novo ambiente onde muitos provavelmente nunca tiveram contato, iremos deixar nessa seção, alguns comandos e atalhos úteis para a navegação e manipulação do sistema, para que assim desenvolvam melhor as suas ideias.

**Comandos:**
- **”pwd”** - Informar qual a partição que está sendo acessada.
- **”ls”** - Listar as pastas e arquivos da partição acessada.
- **”cd <endereço da pasta>”** - Acessar a pasta/partição desejada. Ex: “cd /etc/systemd”; “cd /“ ou “cd /root” (Para acessar a partição principal do sistema)
- **”nano <nome do arquivo>”** - Acessar e modificar o arquivo, ou criar um novo arquivo (certifique-se de estar na pasta correta). Ex: “nano network/“.
- **”blkid”** - Listar tanto o UUID da maquina, quanto o dos dispositivos de memória como pen-drive e cartão microsd conectados.
- **”ping -c <número de vezes> <código DNS>”** - Testar a latência e velocidade da rede. Ex: ping -c 4 8.8.8.8 (ele pegará a velocidade em ms da internet 4 vezes, usando o DNS do Google, que é mais recomendado)

**Atalhos:**
- **”Ctrl + L”** - Limpa toda a interface removendo as mensagens dos comandos.
- **”Tab”** - No Linux, sempre que você começa a escrever um comando ou nome de pasta/arquivo e pressiona o Tab, a linha é completada automaticamente.
- **”Ctrl + O”** - Dentro do ambiente nano (editar/criar arquivos), use este atalho para salvar.
- **”Ctrl + X”** - Dentro do ambiente nano (editar/criar arquivos), use este atalho para sair.
- **”Ctrl + Alt + (F1 até F6)”** - Trocar entre os terminais virtuais “TTY” (simplificando: são como se fossem as áreas de trabalho no Windows, são outras telas limpas para você poder rodar outros comandos ou aplicações).

**Agora o resto é com vocês, não deixaremos uma lista tão extensa para que vocês possam se virar e aprender por conta própria sobre mais funcionalidades desse sistema. Se divirtam descobrindo e desejamos boa sorte para todos vocês.**
