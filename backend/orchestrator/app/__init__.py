import warnings

# `supervision` emite este aviso al importarse; no es de nuestro código.
warnings.filterwarnings("ignore", message=".*template_mgs.*", category=FutureWarning)
