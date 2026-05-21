# 📥 │ Download da imagem Pura (Debian 13):
- https://github.com/devmfc/debian-on-amlogic

Obs: A imagem apresentada costuma receber atualizações constantemente, por este motivo apresentamos o link do próprio github ao invés do arquivo de instalação.
## 🛠️ │ Tutorial de instalação e uso da imagem:
- https://youtu.be/CHj3oQ6NWrk?si=qEjFNMQd9Fwh5Vss

# 📥 │ Download da imagem Modificada/Pronta (Debian 13):
- https://drive.google.com/file/d/1zeyZRLyZpribU1myd3DvLSqR--pgOzRY/view?usp=sharing

⚠️ Atenção: A imagem apresentada está com um problema relacinado ao armazenamento total do dispositivo de memória, siga o procedimento abordado abaixo se forem utilizar essa imagem.
## 🛠️ │ Tutorial para Realocação de 100% da Memória:
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
