# Chunks — CleoIA

## ¿Qué es un chunk?

Un *chunk* es un fragmento de texto de tamaño acotado que se extrae de un
documento más largo. En lugar de indexar un PDF completo como un solo bloque,
el documento se divide en varios chunks —cada uno de unas 450 palabras en
CleoIA— para que cada fragmento sea lo suficientemente pequeño como para
convertirse en un embedding preciso, y lo suficientemente grande como para
conservar sentido por sí solo.

En CleoIA, cada chunk conserva:

- el encabezado (título o subtítulo) de la sección a la que pertenece,
- el texto de esa sección, respetando siempre los límites de las oraciones
  (nunca se corta una oración a la mitad),
- metadatos que lo vinculan de vuelta a su documento y categoría de origen
  (`chunk_id`, `document_id`, `categoria`, `titulo_documento`).

## ¿Qué es el overlap?

El *overlap* (superposición) es la cantidad de texto que se repite entre el
final de un chunk y el comienzo del siguiente. En CleoIA se usa un overlap de
80 palabras.

Sin overlap, una idea que quede justo en el límite entre dos chunks (por
ejemplo, una explicación que empieza en un chunk y termina en el siguiente)
podría perder coherencia al recuperarse de forma aislada. Repitiendo las
últimas ~80 palabras de un chunk al inicio del siguiente, ambos fragmentos
conservan suficiente contexto para tener sentido de forma independiente.

## ¿Por qué son necesarios los chunks en un sistema RAG?

Un sistema RAG (Retrieval-Augmented Generation) no le pasa al modelo de
lenguaje toda la biblioteca de documentos en cada pregunta —sería demasiado
texto y saldría carísimo e ineficiente—. En su lugar:

1. Cada chunk se convierte en un embedding (un vector numérico que
   representa su significado).
2. Cuando el usuario hace una pregunta, esa pregunta también se convierte en
   un embedding.
3. El sistema busca, entre todos los embeddings de chunks guardados en
   Supabase, los que son más similares a la pregunta.
4. Solo esos pocos chunks relevantes se le entregan al modelo como contexto
   para generar la respuesta.

Si los chunks fueran demasiado grandes (documentos completos), la búsqueda
perdería precisión: un documento entero rara vez trata un único tema, así
que su embedding sería una mezcla difusa de muchos temas distintos. Si fueran
demasiado pequeños (por ejemplo, una sola oración), se perdería el contexto
necesario para que la respuesta tenga sentido. El tamaño de 450 palabras con
80 de overlap busca ese equilibrio.

## ¿Cómo usará CleoIA estos fragmentos para responder preguntas?

1. **Indexación**: cada chunk generado en este capítulo (guardado en
   `library/chunks/<categoria>/*.json`) se convertirá en un embedding y se
   almacenará en la tabla `document_chunks` de Supabase (ver
   [`docs/02_Supabase.md`](02_Supabase.md)).
2. **Consulta del usuario**: cuando alguien le pregunte algo a CleoIA (por
   ejemplo, "¿qué colores debo evitar si tengo subtono frío?"), esa pregunta
   se convierte también en un embedding.
3. **Búsqueda semántica**: se comparan los embeddings de la pregunta contra
   los de todos los chunks, y se recuperan los más similares —típicamente
   los que hablan del mismo tema, aunque no usen exactamente las mismas
   palabras—.
4. **Generación de la respuesta**: los chunks recuperados se le entregan como
   contexto al modelo de lenguaje (Cloudflare AI / Qwen), que redacta una
   respuesta fundamentada en el contenido real de la biblioteca, en lugar de
   inventar una respuesta genérica.

> Este capítulo solo genera los chunks y su índice. La generación de
> embeddings y su carga en Supabase se implementarán en un capítulo
> posterior.
