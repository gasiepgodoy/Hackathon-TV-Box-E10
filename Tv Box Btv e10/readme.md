O modelo de TV Box que será utilizado nesse evento Hackathon é o BTV E10. Todas as equipes utilizarão a mesma TV Box e receberão kits (fonte, cabo, cartão de memória, etc) para desenvolvimento com o mesmo conteúdo.
<img width="235" height="423" alt="image" src="https://github.com/user-attachments/assets/83125c95-5693-41db-b814-fbb55277a59c" />

Mais informações sobre o modelo da Tv Box pode ser encontrado em: https://github.com/educabox/educabox/blob/main/boxes/btve10.md

O acesso às Tv Box dentro da Unesp Sorocab já está previamente cadastrado na imagem recomendada.
Para esse acesso (ssh) será necessário utilizar os seguintes dados de acordo com sua Tv Box recebida:
1) Verifique o código mostrado em vermelho no verso da sua Tv Box conforme a imagem:
<img width="1280" height="720" alt="MAC-TvBox" src="https://github.com/user-attachments/assets/01846e24-450e-4fd3-9893-cd28b5c71888" />

2) Verifique o endereço de rede a ser usado para a conexão com sua Tv Box:
<img width="910" height="193" alt="image" src="https://github.com/user-attachments/assets/d969c068-b2f5-4950-9b66-33d786a4ece7" />

3) Use o seu respectivo endereço de rede, depedendo da conexão usada na Unesp Sorocaba (via cabo de rede ou via Wi-Fi), para conexão via ssh com sua TV Box. No caso de uso do Wi-Fi, conectar o adaptador USB-WiFi na porta USB 2.0 (preta) da Tv Box conforme abaixo:
<img width="225" height="400" alt="WhatsApp Image 2026-05-29 at 18 08 56" src="https://github.com/user-attachments/assets/1158949a-2f92-4dce-b200-7af3c2d50b2a" />

4) Ligue a Tv Box na tomada com a fonte fornecida e o cartão de memória conectado no slot da Tv Box. A Tv Box irá ligar e inicializar o sistema operacional (OS) contido no cartão de memória. É possível verificar se a Tv Box ligou verificando se há três (3) luzes vermelhas acessas na fernte da Tv Box.
<img width="225" height="400" alt="WhatsApp Image 2026-05-29 at 18 12 43" src="https://github.com/user-attachments/assets/3867ae70-5b82-4bcb-8354-3f274d7919d1" />

5) Para acesso remoto via rede (ssh) do seu computador (tablet, notebook) para a Tv Box ligada, useu um software de acesso"ssh" como o Putty. Utilize o respectivo endereço de rede da sua Tv Box:
<img width="640" height="360" alt="Putty-TvBox" src="https://github.com/user-attachments/assets/82941e07-85fd-4864-beaa-5efeaebf7d41" />

6) Ao abrir a conexão 'ssh' com a Tv Box, digite o login e senha da Tv Box. O acesso será concedido ao Linux Debian da Tv Box e vc poderá ver informações sobre o SO rodando na Tv Box e acessar o prompt de comando para desenvolvimento.
<img width="4759" height="1125" alt="image" src="https://github.com/user-attachments/assets/045dc5c2-2047-4c01-95ec-e3eac9dac64d" />

7) Pronto!!! Sua Tv Box está pronta para desenvolvimento da sua aplicação. Mãos à obra!!!
Obs: Caso seja necessário utilizar a Tv Box em outro local fora da Unesp, será necessário conectá-la a outra rede (ou Wi-Fi) e acessar seu endereço nessa rede via ssh.


   
   



