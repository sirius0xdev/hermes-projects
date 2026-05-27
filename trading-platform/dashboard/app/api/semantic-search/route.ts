import { NextRequest, NextResponse } from 'next/server';

const EMBEDDING_SERVICE = process.env.EMBEDDING_SERVICE_URL || 'http://embedding-service:8000';

export async function GET(request: NextRequest) {
  const { searchParams } = request.nextUrl;
  const q = searchParams.get('q');
  const entity_type = searchParams.get('entity_type') || undefined;
  const date_from = searchParams.get('date_from') || undefined;
  const date_to = searchParams.get('date_to') || undefined;
  const min_similarity = searchParams.get('min_similarity');
  const top_k = searchParams.get('top_k');

  if (!q || q.trim().length < 2) {
    return NextResponse.json(
      { results: [], total: 0, error: 'Query must be at least 2 characters' },
      { status: 400 }
    );
  }

  try {
    // Step 1: Generate embedding for the query
    const embedRes = await fetch(`${EMBEDDING_SERVICE}/v1/embeddings`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ input: q.trim() }),
      cache: 'no-store',
    });

    if (!embedRes.ok) {
      const errText = await embedRes.text().catch(() => '');
      return NextResponse.json(
        { results: [], total: 0, error: `Embedding service error (${embedRes.status}): ${errText}` },
        { status: embedRes.status }
      );
    }

    const embedData = await embedRes.json();
    const query_embedding = embedData.data?.[0]?.embedding;

    if (!query_embedding) {
      return NextResponse.json(
        { results: [], total: 0, error: 'No embedding returned' },
        { status: 502 }
      );
    }

    // Step 2: Search the vector index
    const searchBody: Record<string, unknown> = {
      query_embedding,
      top_k: top_k ? parseInt(top_k, 10) : 20,
    };
    if (entity_type) searchBody.entity_type = entity_type;
    if (date_from) searchBody.date_from = date_from;
    if (date_to) searchBody.date_to = date_to;
    if (min_similarity) searchBody.min_similarity = parseFloat(min_similarity);

    const searchRes = await fetch(`${EMBEDDING_SERVICE}/v1/search`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(searchBody),
      cache: 'no-store',
    });

    if (!searchRes.ok) {
      const errText = await searchRes.text().catch(() => '');
      return NextResponse.json(
        { results: [], total: 0, error: `Search service error (${searchRes.status}): ${errText}` },
        { status: searchRes.status }
      );
    }

    const searchData = await searchRes.json();

    // Normalize results for the frontend
    const results = (searchData.results || []).map((r: any) => ({
      id: r.entity_id,
      entityType: r.entity_type,
      text: r.text,
      score: r.score,
      timestamp: r.timestamp,
      metadata: r.metadata || {},
    }));

    return NextResponse.json({
      results,
      total: results.length,
      query: q.trim(),
    });
  } catch (error) {
    console.error('[Semantic Search] Proxy error:', error);
    return NextResponse.json(
      { results: [], total: 0, error: 'Internal server error' },
      { status: 500 }
    );
  }
}
