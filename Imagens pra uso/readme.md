# 📥 │ Imagem do Sistema Operacional para a Tv Box

O hardware da Tv Box necessita de um sistema operacional (OS) para habilitar seu uso e desenvolvimento do projeto. Esse software do OS deve ser adequado para permitr que a solução tecnológica a ser desenvolvida opere de maneira satisfatória considerando a capacidade de processamento do hardware da Tv Box.

Esse OS pode ser baseado em Linux ou em Android por exemplo. O grande desafio é encontrar uma ditribuição do OS de interesse que rode de forma adequada no hardware da Tv Box. Consideranbdo que cada Tv Box possui um conjunto de hardware (processador, memória RAM, periféricos e interfaces áudio e vídeo e de conexão de rede) diferentes, a tarefa de encontrar um OS compatível pode se tornar desafiadora. Por exemplo versões difernetes de um mesmo OS Linux ou Android podem utilizar os recursos computacionais do hardware da Tv Box (% da memória RAM e da CPU) de maneira distintas, impactando o desenvolvimento. Adicionalmente, versões difernetes de um mesmo OS Linux ou Android não reconhecer (por ausêncioa de driver compatível ou otimizado por exemplo) algum recurso ou periférico da Tv Box.

Para auxiliar nesse processo, a comissão organzadora do evento está disponibilizando e indicando o uso de um OS Linux baseado numa distribuição Debian 13 para o desenvolvimento do projeto pelas equipes. A imagem desse OS está otimizado e pronta para uso pela Tv Box BTV E10 usada no Hackathon. É uma recomendação e as equipes podem a seus critérios buscarem outros OS para serem usados.

Essa imagem recomenda é do tipo "server" (sem interface gráfica) para minimizar o uso dos recursos computacionaios da TV Box.
OBSERVAÇÃO 1: As equipes receberão as TV Box para desenvolvimento do seu projeto já com essa imagem recomendada pronta para uso em seus cartões de memória. Portantoi, a não ser que seja necessário trocar a imagem ou reiniciar (formatar) a imagem da TV Box para o desenvolvimento do projeto, não será necessário a reralização dos procedimentos abaixo. 

OBSERVAÇÃO 2: As Tv Box foram customizadas para realizar prioritariamente a inicialização (boot) do OS pelo cartão de memória. ATENÇÃO!!! Recomendamos o uso do cartão de memória fornecido junto com as TV Box para facilitar o desenvolvimento dos projetos da equipes. Em caso de problemas com o desenvolvimento, somente é necessário tirar o cartão de memória e regravar a imagem recomendada ou alguma imagem de backup que a equipe eventualmente tenha feito durante o desenvolvimento. NÃO indicamos o desenvolvimento do projeto usando a memória interna da Tv Box.

# 📥 │ Download da imagem Pura (Debian 13):
- https://github.com/devmfc/debian-on-amlogic

Obs: A imagem apresentada costuma receber atualizações constantemente, por este motivo apresentamos o link do próprio github ao invés do arquivo de instalação.
Essa imagem original do OS é bastante simlificada, não incorporando mesmo pacotes báscios do Linux. Para auxiliar no desenvolvimento, a comissão oirganizadora preparou uma imagem modificada, já incorporando pacotes báscios e funcionalidade de rede, a qual é recomendada para uso.

### 🛠️ │ Tutorial de instalação e uso da imagem:
- https://youtu.be/CHj3oQ6NWrk?si=qEjFNMQd9Fwh5Vss

# 📥 │ Recomendado - Download da imagem Modificada/Pronta (Debian 13):
- https://drive.google.com/file/d/1zeyZRLyZpribU1myd3DvLSqR--pgOzRY/view?usp=sharing

⚠️ Atenção: Essa imagem apresentada foi compactada (iumage.xz) para reduzir seu tamanho. Devido à essa compactação, ao gravar essa imagem no cartãso de memória da Tv Box, a imagem não é exppandida para o espaço disponívbel no cartão de memória. Isso não traz impactos de desempenhio da Tv Box, somente em espaço de armazenamento. Para expandir o espaço de armazenamento para todo o espaço disponível do cartão de memória, siga o procedimento abordado abaixo.
### 🛠️ │ Tutorial para Realocação de 100% da Memória:
**Visualizar os discos e partições da memória:**
- `lsblk`

**Exemplo de saída esperada:**

```bash
NAME         MAJ:MIN RM  SIZE RO TYPE MOUNTPOINTS
mmcblk0      179:0    0 28.9G  0 disk 
├─mmcblk0p1  179:1    0  256M  0 part /boot
└─mmcblk0p2  179:2    0 28.6G  0 part /
mmcblk1      179:32   0  7.1G  0 disk 
├─mmcblk1p1  179:33   0  512M  0 part 
└─mmcblk1p2  179:34   0  5.2G  0 part 
mmcblk1boot0 179:64   0    4M  1 disk 
mmcblk1boot1 179:96   0    4M  1 disk
```

**Como ler esse resultado para se proteger:**
1. Olhe para a coluna SIZE (Tamanho).
2. O disco que mostrar algo perto de 29.9G ou 32G é o seu Cartão de Memória. Veja o nome dele na esquerda (no exemplo acima, é o `mmcblk0`).
3. O disco que mostrar o tamanho da memória interna da TV Box (geralmente 7.4G, 16G ou 64G) é a eMMC. Veja o nome dele (no exemplo, `mmcblk1`).

**Quase sempre a lógica do sistema operacional funciona assim:**
- `/dev/mmcblk0` → Geralmente é o primeiro dispositivo de armazenamento inicializado (no seu caso, o Cartão MicroSD onde o Debian deu o boot).
- `/dev/mmcblk1` → Geralmente é o segundo dispositivo (a memória interna eMMC da TV Box).

**⚠️ Atenção:** Em algumas TV Boxes raras, essa ordem pode se inverter. Por isso, nunca devemos rodar comandos de partição às cegas. Por estarem utilizando a nossa e imagem e dispositivo, muito provavelmente podem só copiar e colar o comano abaixo sem se preocupar.

**Expandir o armazenamento:**
- `parted /dev/mmcblk0 resizepart 2 100% && resize2fs /dev/mmcblk0p2`

**O que esse comando vai fazer?**
1. `parted /dev/mmcblk0 resizepart 2 100%`: Vai esticar fisicamente a partição número 2 até o final do cartão de memória (100% do espaço disponível).
2. `&&`: Se o primeiro passo der certo, ele aciona o próximo comando.
3. `resize2fs /dev/mmcblk0p2`: Vai expandir o sistema de arquivos do Debian para que ele passe a enxergar e usar o novo espaço que o comando anterior liberou.

**Ao terminar, você pode verificar se o espaço total apareceu digitando:**
- `df -h` ou `lsblk`

A linha que aponta para / deve mostrar agora algo perto de 29 GB ou 30 GB livres!

(**Nota:** Se o comando do parted reclamar de algo como "Partition 2 is being used", pode dar um "Fix" ou "Ok", pois o Linux moderno consegue redimensionar partições mesmo com o sistema rodando).
