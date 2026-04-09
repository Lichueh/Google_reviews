"""
Semantic network construction and analysis using networkx.
Converts collocation data into weighted graphs with structural metrics.
"""

import networkx as nx


def build_network(collocations: list[dict], word_freq: dict = None) -> nx.Graph:
    """
    Build a weighted undirected graph from collocation results.

    Args:
        collocations: List of dicts with w1, w2, freq, score keys.
        word_freq: Optional dict mapping word -> corpus frequency (for node sizing).

    Returns:
        networkx.Graph with node/edge attributes.
    """
    G = nx.Graph()

    for c in collocations:
        w1, w2 = c['w1'], c['w2']
        G.add_edge(w1, w2, weight=c['score'], freq=c['freq'])

    # Set node attributes
    if word_freq:
        for node in G.nodes():
            G.nodes[node]['freq'] = word_freq.get(node, 1)
    else:
        # Estimate from edge frequencies
        for node in G.nodes():
            G.nodes[node]['freq'] = sum(
                d.get('freq', 1) for _, _, d in G.edges(node, data=True)
            )

    return G


def compute_metrics(G: nx.Graph) -> dict:
    """Compute structural metrics for a network."""
    if G.number_of_nodes() == 0:
        return {
            'node_count': 0, 'edge_count': 0, 'density': 0,
            'avg_clustering': 0, 'components': 0,
            'top_degree': [], 'top_betweenness': [],
        }

    degree_cent = nx.degree_centrality(G)
    betweenness_cent = nx.betweenness_centrality(G, weight='weight')

    top_degree = sorted(degree_cent.items(), key=lambda x: x[1], reverse=True)[:10]
    top_betweenness = sorted(betweenness_cent.items(), key=lambda x: x[1], reverse=True)[:10]

    return {
        'node_count': G.number_of_nodes(),
        'edge_count': G.number_of_edges(),
        'density': round(nx.density(G), 4),
        'avg_clustering': round(nx.average_clustering(G, weight='weight'), 4),
        'components': nx.number_connected_components(G),
        'top_degree': [{'word': w, 'centrality': round(c, 4)} for w, c in top_degree],
        'top_betweenness': [{'word': w, 'centrality': round(c, 4)} for w, c in top_betweenness],
    }


def to_vis_json(G: nx.Graph) -> dict:
    """
    Export network to vis.js compatible JSON format.

    Returns:
        {
            "nodes": [{"id": str, "label": str, "value": int, "centrality": float}, ...],
            "edges": [{"from": str, "to": str, "value": float, "title": str}, ...],
            "metrics": {...}
        }
    """
    if G.number_of_nodes() == 0:
        return {'nodes': [], 'edges': [], 'metrics': compute_metrics(G)}

    degree_cent = nx.degree_centrality(G)
    betweenness_cent = nx.betweenness_centrality(G, weight='weight')

    # Compute community detection for coloring
    try:
        communities = nx.community.greedy_modularity_communities(G, weight='weight')
        node_community = {}
        for i, comm in enumerate(communities):
            for node in comm:
                node_community[node] = i
    except Exception:
        node_community = {n: 0 for n in G.nodes()}

    nodes = []
    for node in G.nodes():
        nodes.append({
            'id': node,
            'label': node,
            'value': G.nodes[node].get('freq', 1),
            'degree_centrality': round(degree_cent.get(node, 0), 4),
            'betweenness_centrality': round(betweenness_cent.get(node, 0), 4),
            'community': node_community.get(node, 0),
        })

    edges = []
    for u, v, data in G.edges(data=True):
        edges.append({
            'from': u,
            'to': v,
            'value': round(data.get('weight', 1), 4),
            'freq': data.get('freq', 1),
            'title': f"{u} — {v} (score: {data.get('weight', 0):.2f}, freq: {data.get('freq', 0)})",
        })

    return {
        'nodes': nodes,
        'edges': edges,
        'metrics': compute_metrics(G),
    }
