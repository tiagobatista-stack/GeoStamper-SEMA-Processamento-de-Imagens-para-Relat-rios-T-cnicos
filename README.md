GeoStamper 

Este projeto nasceu para resolver um problema comum em vistorias ambientais: informações de GPS das imagens de drone, fotos tiradas com celular que não possuem estampa previamente obtidas para inserção no relatório técnico

O script automatiza o carimbo de coordenadas, altitude e data diretamente na imagem, usando um layout de alto contraste feito para ser lido sem esforço, seja na tela do computador ou no relatório impresso.

Por que isso ajuda no trabalho?
Diferente de outros carimbos automáticos, este foi calibrado especificamente para imagens que serão compactadas em documentos PDF ou Word. Ele compensa o tamanho das fontes e usa o padrão de cores (preto e amarelo) que é referência em leitura técnica. Isso evita que você tenha que editar as fotos manualmente ou anexar tabelas de GPS separadas.

O que ele faz
Lê o invisível: Extrai Latitude, Longitude e Altitude direto dos arquivos originais do drone ou celular.

Cria o carimbo: Gera uma barra inferior robusta (24% da altura da foto) para os dados respirarem.

Protege a leitura: Ajusta o tamanho do texto para que a data e a hora nunca fiquem em cima das coordenadas.

Como rodar
Basta instalar as bibliotecas (pip install Pillow matplotlib), colocar suas fotos na pasta e rodar o geo_stamper.py.
