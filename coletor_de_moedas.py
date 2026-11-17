import arcade
import random
import os
import math
import time
import datetime

from PIL import Image, ImageOps

from peewee import (
    SqliteDatabase,
    Model,
    CharField,
    IntegerField,
    FloatField,
    DateTimeField
)

# =====================================================
# CONFIGURAÇÕES
# =====================================================
DIRETORIO_ATUAL = os.path.dirname(os.path.abspath(__file__))

LARGURA = 800
ALTURA = 600

GRAVIDADE = 0.5
VELOCIDADE = 5
FORCA_PULO = 16
PONTUACAO_VITORIA = 25
TAMANHO_BLOCO = 64  # largura do bloco em pixels
VIDAS_INICIAIS = 3  # vidas do jogador
DURACAO_DANO = 0.8  # segundos de choro/tela vermelha ao tomar dano

ALTURA_JOGADOR = 64   # altura do personagem em pixels (na tela)

# SPRITESHEET DO JOGADOR (quadros 0..8 na ordem de leitura)
ARQUIVO_SPRITESHEET = "spritesheet.png"
LARGURA_QUADRO = 45
ALTURA_QUADRO = 59
# quadro 0 = parado | 1-4 = correndo | 5-8 = pulando


def carregar_imagem(nome):
    return arcade.load_texture(
        os.path.join(DIRETORIO_ATUAL, nome)
    )


# =====================================================
# BANCO DE DADOS
# =====================================================
banco = SqliteDatabase(
    os.path.join(DIRETORIO_ATUAL, "ranking.db")
)


class BaseModel(Model):
    class Meta:
        database = banco


class Pontuacao(BaseModel):
    nome_jogador = CharField()
    pontos = IntegerField()
    tempo_partida = FloatField()
    data_hora = DateTimeField(
        default=datetime.datetime.now
    )

    def __str__(self):
        return (
            f"{self.nome_jogador} - {self.pontos} pts "
            f"({self.tempo_partida:.1f}s)"
        )

    @classmethod
    def registrar(cls, nome, pontos, tempo):
        """Create: grava uma nova pontuação no banco."""
        return Pontuacao.create(
            nome_jogador=nome,
            pontos=pontos,
            tempo_partida=tempo
        )

    @classmethod
    def top10(cls):
        """Read: retorna as 10 maiores pontuações."""
        return list(
            Pontuacao.select()
            .order_by(Pontuacao.pontos.desc())
            .limit(10)
        )


banco.connect(reuse_if_open=True)
banco.create_tables([Pontuacao])


# =====================================================
# BLOCO
# =====================================================
class Bloco(arcade.Sprite):

    def __init__(self, x, y):
        textura = carregar_imagem("blocox.png")

        # Ajusta a escala para o bloco ter sempre TAMANHO_BLOCO de largura,
        # independente do tamanho original da imagem
        super().__init__(
            textura,
            scale=0.3
        )

        self.center_x = x
        self.center_y = y


# =====================================================
# JOGADOR
# =====================================================
class Jogador(arcade.Sprite):

    def __init__(self):

        spritesheet = arcade.load_spritesheet(
            os.path.join(DIRETORIO_ATUAL, ARQUIVO_SPRITESHEET)
        )

        # Colunas e linhas calculadas a partir do tamanho real da imagem
        largura_img, altura_img = spritesheet.image.size

        colunas = largura_img // LARGURA_QUADRO
        linhas = altura_img // ALTURA_QUADRO

        print(
            f"[{ARQUIVO_SPRITESHEET}] imagem: {largura_img}x{altura_img} | "
            f"{colunas} colunas x {linhas} linhas de "
            f"{LARGURA_QUADRO}x{ALTURA_QUADRO}"
        )

        texturas = spritesheet.get_texture_grid(
            size=(LARGURA_QUADRO, ALTURA_QUADRO),
            columns=colunas,
            count=colunas * linhas
        )

        if len(texturas) < 9:
            raise ValueError(
                f"A spritesheet tem so {len(texturas)} quadros, "
                f"mas o jogo precisa de 9."
            )

        super().__init__(
            texturas[0],
            scale=1.4
        )

        # Versao espelhada de cada quadro (para olhar para a esquerda).
        # Os quadros sao recortados na mesma ordem do get_texture_grid.
        texturas_esquerda = []

        for i in range(len(texturas)):

            coluna = i % colunas
            linha = i // colunas

            x = coluna * LARGURA_QUADRO
            y = linha * ALTURA_QUADRO

            quadro = spritesheet.image.crop(
                (x, y, x + LARGURA_QUADRO, y + ALTURA_QUADRO)
            )

            texturas_esquerda.append(
                arcade.Texture(ImageOps.mirror(quadro))
            )

        self.quadros = {
            "direita": texturas,
            "esquerda": texturas_esquerda
        }

        self.virado_para = "direita"

        self.indice_animacao = 0
        self.tempo_animacao = 0

        self.esta_chorando = False

        # Imagem de choro redimensionada para a mesma altura dos outros quadros
        imagem_choro = Image.open(
            os.path.join(DIRETORIO_ATUAL, "textura_chorox.png")
        ).convert("RGBA")

        proporcao = ALTURA_QUADRO / imagem_choro.height

        imagem_choro = imagem_choro.resize(
            (max(1, round(imagem_choro.width * proporcao)), ALTURA_QUADRO)
        )

        self.textura_choro = arcade.Texture(imagem_choro)

    def update(self, delta_time=0):

        if self.change_x > 0:
            self.virado_para = "direita"

        elif self.change_x < 0:
            self.virado_para = "esquerda"

        quadros = self.quadros[self.virado_para]

        # PRIORIDADE 1: PULO/QUEDA (change_y != 0) - o quadro depende da velocidade vertical

        if self.change_y != 0:

            if self.change_y > 8:
                indice = 0      # saindo do chao
            elif self.change_y > 0:
                indice = 1      # subindo
            elif self.change_y > -8:
                indice = 2      # no topo / comecando a cair
            else:
                indice = 3      # caindo

            self.texture = quadros[5 + indice]

        # PRIORIDADE 2: PARADO

        elif self.change_x == 0:

            self.texture = quadros[0]

            self.indice_animacao = 0
            self.tempo_animacao = 0

        # PRIORIDADE 3: ANDANDO

        else:

            self.tempo_animacao += delta_time

            if self.tempo_animacao >= 0.1:

                self.tempo_animacao -= 0.1

                self.indice_animacao += 1

                if self.indice_animacao >= 4:
                    self.indice_animacao = 0

            self.texture = quadros[1 + self.indice_animacao]

        # CHORO

        if self.esta_chorando:
            self.texture = self.textura_choro


# =====================================================
# INIMIGO
# =====================================================
class Inimigo(arcade.Sprite):

    def __init__(self):
        super().__init__(
            os.path.join(DIRETORIO_ATUAL, "maex.png"),
            scale=0.1
        )

    def update(self, delta_time=0):

        if self.right >= LARGURA:
            self.right = LARGURA
            self.change_x = -abs(self.change_x)

        elif self.left <= 0:
            self.left = 0
            self.change_x = abs(self.change_x)


# =====================================================
# INIMIGO PERSEGUIDOR
# =====================================================
class InimigoPerseguidor(arcade.Sprite):

    def __init__(self, jogador_alvo):
        super().__init__(
            os.path.join(DIRETORIO_ATUAL, "chinelox.png"),
            scale=0.2
        )

        self.jogador = jogador_alvo
        self.velocidade = 2

    def update(self, delta_time=0):

        dx = self.jogador.center_x - self.center_x
        dy = self.jogador.center_y - self.center_y

        distancia = math.sqrt(dx ** 2 + dy ** 2)

        if distancia > 0:

            self.change_x = dx / distancia * self.velocidade
            self.change_y = dy / distancia * self.velocidade

        self.center_x += self.change_x
        self.center_y += self.change_y


# =====================================================
# MOEDA
# =====================================================
class Moeda(arcade.Sprite):

    def __init__(self):
        super().__init__(
            os.path.join(DIRETORIO_ATUAL, "moedax.png"),
            scale=0.09
        )

    def update(self, delta_time=0):

        self.center_x += self.change_x
        self.center_y += self.change_y

        if self.right > LARGURA or self.left < 0:
            self.change_x *= -1

        if self.top > ALTURA or self.bottom < 0:
            self.change_y *= -1


# =====================================================
# TELA INICIAL
# =====================================================
class TelaInicial(arcade.View):

    def __init__(self):
        super().__init__()

        self.fundo = carregar_imagem("fundo1.png")

    def on_draw(self):

        self.clear()

        arcade.draw_texture_rect(
            self.fundo,
            arcade.XYWH(
                LARGURA / 2,
                ALTURA / 2,
                LARGURA,
                ALTURA
            )
        )

        arcade.draw_text(
            "Jogo - O Coletor de Moedas",
            LARGURA / 2, 400,
            arcade.color.WHITE, 22,
            anchor_x="center"
        )

        arcade.draw_text(
            "Controles: A, D e W",
            LARGURA / 2, 340,
            arcade.color.WHITE, 18,
            anchor_x="center"
        )

        arcade.draw_text(
            "Pressione [J] para Jogar",
            LARGURA / 2, 280,
            arcade.color.LIGHT_SEA_GREEN, 18,
            anchor_x="center"
        )

        arcade.draw_text(
            "Pressione [R] para Ranking",
            LARGURA / 2, 230,
            arcade.color.GOLD, 18,
            anchor_x="center"
        )

        arcade.draw_text(
            "Pressione [ESC] para Sair",
            LARGURA / 2, 180,
            arcade.color.LIGHT_SEA_GREEN, 18,
            anchor_x="center"
        )

    def on_key_press(self, key, modifiers):

        if key == arcade.key.J:
            self.window.show_view(TelaJogo())

        elif key == arcade.key.R:
            self.window.show_view(TelaRanking())

        elif key == arcade.key.ESCAPE:
            arcade.exit()


# =====================================================
# TELA DE CADASTRO
# =====================================================
class TelaCadastro(arcade.View):

    def __init__(self, pontos, tempo, mensagem):
        super().__init__()

        self.pontos = pontos
        self.tempo = tempo
        self.mensagem = mensagem

        self.nome = ""
        self.salvo = False

        self.fundo = carregar_imagem("fundo.png")

    def on_draw(self):

        self.clear()

        arcade.draw_texture_rect(
            self.fundo,
            arcade.XYWH(
                LARGURA / 2,
                ALTURA / 2,
                LARGURA,
                ALTURA
            )
        )

        arcade.draw_text(
            self.mensagem,
            LARGURA / 2, 430,
            arcade.color.GOLD, 26,
            anchor_x="center"
        )

        arcade.draw_text(
            f"Pontuação: {self.pontos}",
            LARGURA / 2, 360,
            arcade.color.WHITE, 22,
            anchor_x="center"
        )

        arcade.draw_text(
            f"Tempo: {self.tempo:.1f} segundos",
            LARGURA / 2, 320,
            arcade.color.WHITE, 18,
            anchor_x="center"
        )

        arcade.draw_text(
            "Digite seu nome:",
            LARGURA / 2, 250,
            arcade.color.WHITE, 20,
            anchor_x="center"
        )

        arcade.draw_text(
            self.nome + "_",
            LARGURA / 2, 200,
            arcade.color.LIGHT_SEA_GREEN, 24,
            anchor_x="center"
        )

        arcade.draw_text(
            "Pressione ENTER para salvar",
            LARGURA / 2, 120,
            arcade.color.WHITE, 16,
            anchor_x="center"
        )

        arcade.draw_text(
            "ESC para voltar sem salvar",
            LARGURA / 2, 80,
            arcade.color.WHITE, 14,
            anchor_x="center"
        )

    def on_text(self, text):

        if (
            not self.salvo
            and text.isprintable()
            and len(self.nome) < 20
        ):
            self.nome += text

    def on_key_press(self, key, modifiers):

        if key == arcade.key.BACKSPACE:
            self.nome = self.nome[:-1]

        elif key == arcade.key.ENTER:

            nome_final = self.nome.strip()

            if nome_final and not self.salvo:

                Pontuacao.registrar(
                    nome_final,
                    self.pontos,
                    self.tempo
                )

                self.salvo = True

                print("Pontuação salva com sucesso!")

                self.window.show_view(TelaRanking())

        elif key == arcade.key.ESCAPE:
            self.window.show_view(TelaInicial())


# =====================================================
# TELA DE RANKING
# =====================================================
class TelaRanking(arcade.View):

    def __init__(self):
        super().__init__()

        self.fundo = carregar_imagem("fundo.png")

        # CONSULTA FEITA UMA ÚNICA VEZ

        self.melhores = Pontuacao.top10()

    def on_draw(self):

        self.clear()

        arcade.draw_texture_rect(
            self.fundo,
            arcade.XYWH(
                LARGURA / 2,
                ALTURA / 2,
                LARGURA,
                ALTURA
            )
        )

        arcade.draw_text(
            "RANKING - TOP 10",
            LARGURA / 2, 520,
            arcade.color.GOLD, 30,
            anchor_x="center"
        )

        if not self.melhores:

            arcade.draw_text(
                "Nenhuma pontuação registrada!",
                LARGURA / 2, 350,
                arcade.color.WHITE, 20,
                anchor_x="center"
            )

        else:

            for i, jogador in enumerate(self.melhores):

                texto = (
                    f"{i + 1}º - {jogador.nome_jogador} "
                    f"- {jogador.pontos} pontos "
                    f"- {jogador.tempo_partida:.1f}s"
                )

                arcade.draw_text(
                    texto,
                    LARGURA / 2,
                    450 - i * 35,
                    arcade.color.WHITE,
                    18,
                    anchor_x="center"
                )

        arcade.draw_text(
            "Pressione J para jogar novamente",
            LARGURA / 2, 80,
            arcade.color.LIGHT_SEA_GREEN, 16,
            anchor_x="center"
        )

        arcade.draw_text(
            "Pressione ESC para voltar",
            LARGURA / 2, 45,
            arcade.color.WHITE, 14,
            anchor_x="center"
        )

    def on_key_press(self, key, modifiers):

        if key == arcade.key.J:
            self.window.show_view(TelaJogo())

        elif key == arcade.key.ESCAPE:
            self.window.show_view(TelaInicial())


# =====================================================
# TELA DE JOGO
# =====================================================
class TelaJogo(arcade.View):

    def __init__(self):
        super().__init__()

        self.fundo = carregar_imagem("fundo.png")

        # PLATAFORMAS E CHÃO

        self.sprite_blocos = arcade.SpriteList()

        for x in range(32, LARGURA + 32, 64):

            chao = Bloco(x=x, y=30)
            self.sprite_blocos.append(chao)

        posicoes_plataforma = [
            (300, 250),
            (550, 250)
        ]

        for x, y in posicoes_plataforma:

            plataforma = Bloco(x, y)
            self.sprite_blocos.append(plataforma)

        # CONFIGURAÇÕES

        self.movimento = VELOCIDADE
        self.pontuacao = 0
        self.vidas = VIDAS_INICIAIS

        self.tempo_inicio = time.time()

        self.ja_colidiu_com_inimigo = False
        self.tempo_dano = 0
        self.intensidade_tremor = 5
        self.partida_finalizada = False

        # JOGADOR

        self.personagem = Jogador()
        self.personagem.center_x = 400
        self.personagem.center_y = 300

        self.sprite_jogador = arcade.SpriteList()
        self.sprite_jogador.append(self.personagem)

        # FÍSICA DO JOGADOR

        self.engine_fisica = arcade.PhysicsEnginePlatformer(
            player_sprite=self.personagem,
            walls=self.sprite_blocos,
            gravity_constant=GRAVIDADE
        )

        # INIMIGO

        self.personagem1 = Inimigo()

        self.personagem1.left = random.randint(100, 500)
        self.personagem1.bottom = 400
        self.personagem1.change_x = 1

        self.sprite_inimigo = arcade.SpriteList()
        self.sprite_inimigo.append(self.personagem1)

        # FÍSICA DO INIMIGO

        self.engine_fisica_inimigo = arcade.PhysicsEnginePlatformer(
            player_sprite=self.personagem1,
            walls=self.sprite_blocos,
            gravity_constant=GRAVIDADE
        )

        # INIMIGO PERSEGUIDOR

        self.perseguidor = InimigoPerseguidor(
            self.personagem
        )

        self.perseguidor.center_x = random.choice(
            [50, LARGURA - 50]
        )

        self.perseguidor.center_y = random.choice(
            [100, ALTURA - 50]
        )

        self.sprite_inimigo.append(self.perseguidor)

        # MOEDAS

        self.sprite_moeda = arcade.SpriteList()

        self.moeda_especial = Moeda()
        self.moeda_especial.center_x = 600
        self.moeda_especial.center_y = 500

        self.moeda_especial.change_x = self.movimento
        self.moeda_especial.change_y = self.movimento

        self.sprite_moeda.append(self.moeda_especial)

        for i in range(25):

            moeda_simples = Moeda()

            moeda_simples.center_x = random.randint(
                50, LARGURA - 50
            )

            moeda_simples.center_y = random.randint(
                50, ALTURA - 50
            )

            self.sprite_moeda.append(moeda_simples)

    # FINALIZAR PARTIDA

    def finalizar_partida(self, mensagem):

        if self.partida_finalizada:
            return

        self.partida_finalizada = True

        tempo_total = time.time() - self.tempo_inicio

        self.window.show_view(
            TelaCadastro(
                self.pontuacao,
                tempo_total,
                mensagem
            )
        )

    # DESENHAR JOGO

    def on_draw(self):

        self.clear()

        if self.personagem.esta_chorando:

            deslocamento_x = random.randint(
                -self.intensidade_tremor,
                self.intensidade_tremor
            )

            deslocamento_y = random.randint(
                -self.intensidade_tremor,
                self.intensidade_tremor
            )

        else:
            deslocamento_x = 0
            deslocamento_y = 0

        arcade.draw_texture_rect(
            texture=self.fundo,
            rect=arcade.XYWH(
                LARGURA / 2 + deslocamento_x,
                ALTURA / 2 + deslocamento_y,
                LARGURA,
                ALTURA
            )
        )

        listas = [
            self.sprite_jogador,
            self.sprite_moeda,
            self.sprite_inimigo,
            self.sprite_blocos
        ]

        posicoes_originais = []

        for lista in listas:

            for sprite in lista:

                posicoes_originais.append(
                    (
                        sprite,
                        sprite.center_x,
                        sprite.center_y
                    )
                )

                sprite.center_x += deslocamento_x
                sprite.center_y += deslocamento_y

        self.sprite_jogador.draw()
        self.sprite_moeda.draw()
        self.sprite_inimigo.draw()
        self.sprite_blocos.draw()

        for sprite, x_original, y_original in posicoes_originais:

            sprite.center_x = x_original
            sprite.center_y = y_original

        # TELA VERMELHA AO TOMAR DANO

        if self.personagem.esta_chorando:

            arcade.draw_rect_filled(
                arcade.XYWH(
                    LARGURA / 2,
                    ALTURA / 2,
                    LARGURA,
                    ALTURA
                ),
                (255, 0, 0, 90)
            )

        arcade.draw_text(
            f"Pontos: {self.pontuacao}",
            10 + deslocamento_x,
            ALTURA - 30 + deslocamento_y,
            arcade.color.WHITE,
            16
        )

        arcade.draw_text(
            f"Objetivo: {PONTUACAO_VITORIA}",
            10 + deslocamento_x,
            ALTURA - 55 + deslocamento_y,
            arcade.color.GOLD,
            14
        )

        # CONTADOR DE VIDAS (círculo vermelho = vida, cinza = vida perdida)

        arcade.draw_text(
            "Vidas:",
            10 + deslocamento_x,
            ALTURA - 82 + deslocamento_y,
            arcade.color.WHITE,
            14
        )

        for i in range(VIDAS_INICIAIS):

            if i < self.vidas:
                cor = arcade.color.RED
            else:
                cor = arcade.color.DARK_GRAY

            arcade.draw_circle_filled(
                75 + i * 24 + deslocamento_x,
                ALTURA - 76 + deslocamento_y,
                9,
                cor
            )

    # ATUALIZAR JOGO

    def on_update(self, delta_time):

        if self.partida_finalizada:
            return

        self.sprite_moeda.update(delta_time)

        self.engine_fisica.update()

        self.engine_fisica_inimigo.update()

        # LIMITES DA TELA (evita o jogador sair e cair para fora)

        if self.personagem.left < 0:
            self.personagem.left = 0

        if self.personagem.right > LARGURA:
            self.personagem.right = LARGURA

        if self.personagem.top > ALTURA:
            self.personagem.top = ALTURA

        # Seguranca: se cair abaixo da tela, volta para o centro
        if self.personagem.top < 0:
            self.personagem.center_x = LARGURA / 2
            self.personagem.center_y = 300
            self.personagem.change_y = 0

        self.perseguidor.update(delta_time)

        self.personagem.update(delta_time)

        self.personagem1.update(delta_time)

        # COLISÃO COM PERSEGUIDOR

        if arcade.check_for_collision(
            self.personagem,
            self.perseguidor
        ):

            self.finalizar_partida(
                "GAME OVER! O perseguidor te pegou!"
            )
            return

        # COLISÃO COM INIMIGO

        esta_colidindo_agora = arcade.check_for_collision(
            self.personagem,
            self.personagem1
        )

        if esta_colidindo_agora:

            if not self.ja_colidiu_com_inimigo:

                self.vidas -= 1
                self.ja_colidiu_com_inimigo = True
                self.tempo_dano = DURACAO_DANO

        else:

            self.ja_colidiu_com_inimigo = False

        # O choro e a tela vermelha duram DURACAO_DANO segundos apos o dano
        if self.tempo_dano > 0:
            self.tempo_dano -= delta_time

        self.personagem.esta_chorando = (
            esta_colidindo_agora or self.tempo_dano > 0
        )

        # COLISÃO COM MOEDAS

        moedas_colididas = arcade.check_for_collision_with_list(
            self.personagem,
            self.sprite_moeda
        )

        for moeda in moedas_colididas:

            era_especial = moeda == self.moeda_especial

            moeda.remove_from_sprite_lists()

            if era_especial:
                self.pontuacao += 5
            else:
                self.pontuacao += 1

        # VITÓRIA

        if self.pontuacao >= PONTUACAO_VITORIA:

            self.finalizar_partida(
                "Você venceu! Parabéns!"
            )
            return

        # DERROTA

        if self.vidas <= 0:

            self.finalizar_partida(
                "GAME OVER! Você ficou sem vidas!"
            )
            return

    # CONTROLES

    def on_key_press(self, key, modifiers):

        if key in (arcade.key.RIGHT, arcade.key.D):

            self.personagem.change_x = self.movimento

        elif key in (arcade.key.LEFT, arcade.key.A):

            self.personagem.change_x = -self.movimento

        elif key in (
            arcade.key.UP,
            arcade.key.SPACE,
            arcade.key.W
        ):

            if self.engine_fisica.can_jump():

                self.personagem.change_y = FORCA_PULO

        elif key == arcade.key.ESCAPE:

            self.window.show_view(TelaInicial())

    # PARAR MOVIMENTO

    def on_key_release(self, key, modifiers):

        if key in (
            arcade.key.RIGHT,
            arcade.key.LEFT,
            arcade.key.A,
            arcade.key.D
        ):

            self.personagem.change_x = 0


# =====================================================
# EXECUTAR JOGO
# =====================================================
def executar():

    janela = arcade.Window(
        LARGURA,
        ALTURA,
        "O Coletor de Moedas"
    )

    janela.show_view(TelaInicial())

    arcade.run()


if __name__ == "__main__":
    executar()
