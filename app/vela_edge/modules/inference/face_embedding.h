/* face_embedding.h — Phase 3: face embedding pipeline */
#ifndef FACE_EMBEDDING_H
#define FACE_EMBEDDING_H

/* Run one face embedding inference cycle.
 * Returns 128-d float embedding on success, NULL on error.
 * embedding buffer must be 128 floats.
 */
int face_embedding_run(float embedding[128]);

#endif
