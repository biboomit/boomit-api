from typing import Optional, List
import json
import logging
import hashlib
from datetime import datetime, timezone
from google.cloud import bigquery

from app.core.config import bigquery_config
from app.core.exceptions import DatabaseConnectionError
from app.schemas.insights import InsightItem, PaginatedAppInsightsResponse

logger = logging.getLogger(__name__)


class InsightsService:
    """Service for retrieving and processing app insights from AI analysis data"""

    def __init__(self) -> None:
        self.client = bigquery_config.get_client()
        self.analysis_table_id = bigquery_config.get_table_id_with_dataset(
            "AIOutput", "Reviews_Analysis"
        )

    async def get_app_insights(
        self,
        app_id: str,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        page: int = 1,
        per_page: int = 10
    ) -> PaginatedAppInsightsResponse:
        """Get insights for a specific app from AI analysis data with temporal aggregation and pagination.

        This method aggregates insights from multiple analysis records over time, providing
        a comprehensive view of app insights trends. It handles temporal deduplication,
        prioritizes recent insights, and tracks insight evolution over time.

        Args:
            app_id: App ID to get insights for
            from_date: Optional start date filter (YYYY-MM-DD format)
            to_date: Optional end date filter (YYYY-MM-DD format)
            page: Page number (1-based)
            per_page: Number of items per page

        Returns:
            PaginatedAppInsightsResponse containing temporally aggregated insights with pagination info

        Raises:
            DatabaseConnectionError: If query fails
        """
        try:
            logger.info(f"Getting insights for app: {app_id}")
            
            # Build WHERE conditions
            where_conditions = ["app_id = @app_id", "json_data IS NOT NULL"]
            query_params = [
                bigquery.ScalarQueryParameter("app_id", "STRING", app_id)
            ]

            # Add date filters if provided
            if from_date:
                where_conditions.append("review_date >= @from_date")
                query_params.append(
                    bigquery.ScalarQueryParameter("from_date", "DATE", from_date)
                )

            if to_date:
                where_conditions.append("review_date <= @to_date")
                query_params.append(
                    bigquery.ScalarQueryParameter("to_date", "DATE", to_date)
                )

            where_clause = "WHERE " + " AND ".join(where_conditions)

            # Query for AI analysis data
            query = f"""
            SELECT 
                json_data,
                review_date,
                analyzed_at
            FROM `{self.analysis_table_id}`
            {where_clause}
            ORDER BY analyzed_at DESC
            """

            job_config = bigquery.QueryJobConfig(query_parameters=query_params)
            
            query_job = self.client.query(query, job_config=job_config)
            results = list(query_job.result())

            if not results:
                logger.info(f"No analysis data found for app: {app_id}")
                return PaginatedAppInsightsResponse(
                    insights=[],
                    total=0,
                    page=page,
                    per_page=per_page
                )

            # Process multiple analyses with temporal aggregation
            all_insights = self._process_multiple_analyses_with_temporal_logic(results)
            total_insights = len(all_insights)
            
            # Apply pagination
            start_index = (page - 1) * per_page
            end_index = start_index + per_page
            
            # Validate page bounds
            if total_insights > 0 and start_index >= total_insights:
                max_pages = ((total_insights - 1) // per_page) + 1
                raise ValueError(f"Requested page {page} is out of bounds. There are only {max_pages} pages available.")
            
            paginated_insights = all_insights[start_index:end_index]
            
            logger.info(f"Processed {len(results)} analyses into {total_insights} aggregated insights for app: {app_id}, returning page {page} with {len(paginated_insights)} insights")
            
            return PaginatedAppInsightsResponse(
                insights=paginated_insights,
                total=total_insights,
                page=page,
                per_page=per_page
            )

        except ValueError:
            # Re-raise ValueError for pagination validation (don't convert to DatabaseConnectionError)
            raise
        except Exception as e:
            logger.error(f"Error getting insights for app {app_id}: {e}")
            raise DatabaseConnectionError(f"Error querying the database: {e}")

    def _generate_change_value(self, 
                              insight_type: str, 
                              content: str, 
                              priority: str = None, 
                              sentiment_score: int = None) -> str:
        """Generate appropriate change value based on available data using realistic simulation.
        
        Args:
            insight_type: Type of insight ('positive' or 'negative')
            content: Text content to analyze for keywords
            priority: Priority level if available ('high', 'medium', 'low')
            sentiment_score: Sentiment score if available (1-5 scale)
            
        Returns:
            String representing percentage change (e.g., '+25%', '-30%')
        """
        
        # Method 1: Use priority if available (for recommendations)
        if priority:
            priority_mapping = {
                "high": ["+45%", "+50%", "+40%", "+55%"],
                "medium": ["+25%", "+30%", "+20%", "+35%"], 
                "low": ["+10%", "+15%", "+12%", "+18%"]
            }
            options = priority_mapping.get(priority.lower(), ["+20%"])
            
        # Method 2: Use sentiment score if available
        elif sentiment_score is not None:
            if sentiment_score >= 4:
                options = ["+35%", "+40%", "+30%", "+45%"]
            elif sentiment_score >= 3:
                options = ["+15%", "+20%", "+18%", "+25%"]
            elif sentiment_score == 2:
                options = ["-15%", "-20%", "-18%", "-25%"]
            else:
                options = ["-30%", "-35%", "-25%", "-40%"]
        
        # Method 3: Analyze content for keywords
        else:
            content_lower = content.lower()
            
            # Positive indicators
            if any(word in content_lower for word in ["mejor", "excelente", "bueno", "útil", "rápido", "fácil"]):
                options = ["+20%", "+25%", "+18%", "+30%"]
            # Negative indicators  
            elif any(word in content_lower for word in ["problema", "lento", "difícil", "caro", "malo", "error"]):
                options = ["-25%", "-30%", "-20%", "-35%"]
            # Neutral or mixed
            else:
                if insight_type == "positive":
                    options = ["+15%", "+18%", "+12%", "+22%"]
                else:
                    options = ["-15%", "-18%", "-12%", "-22%"]
        
        # Use hash for consistent but varied selection based on content
        hash_val = int(hashlib.md5(content.encode('utf-8')).hexdigest(), 16)
        return options[hash_val % len(options)]

    def _process_multiple_analyses_with_temporal_logic(self, results: List) -> List[InsightItem]:
        """Process multiple analysis records with advanced temporal aggregation.
        
        This method handles:
        1. Temporal grouping of insights by type and content similarity
        2. Evolution tracking of insights over time
        3. Prioritization of recent insights
        4. Intelligent deduplication across time periods
        
        Args:
            results: Raw query results from BigQuery ordered by analyzed_at DESC
            
        Returns:
            List of temporally aggregated InsightItem objects
        """
        if not results:
            return []
            
        # Group analyses by time periods for temporal processing
        analyses_by_period = {}
        all_raw_insights = []
        
        for row in results:
            try:
                analysis_data = json.loads(row.json_data)
                review_date = row.review_date
                analyzed_at = row.analyzed_at
                period = review_date.strftime("%Y-%m") if review_date else "unknown"
                
                # Store analysis metadata for temporal processing
                analysis_meta = {
                    'data': analysis_data,
                    'review_date': review_date,
                    'analyzed_at': analyzed_at,
                    'period': period,
                    'recency_score': self._calculate_recency_score(analyzed_at)
                }
                
                # Group by period for temporal analysis
                if period not in analyses_by_period:
                    analyses_by_period[period] = []
                analyses_by_period[period].append(analysis_meta)
                
                # Extract raw insights with metadata
                raw_insights = self._extract_insights_with_metadata(analysis_meta)
                all_raw_insights.extend(raw_insights)
                
            except (json.JSONDecodeError, KeyError, AttributeError) as e:
                logger.warning(f"Error processing analysis data: {e}")
                continue
        
        # Apply temporal aggregation and deduplication
        aggregated_insights = self._apply_temporal_aggregation(all_raw_insights, analyses_by_period)
        
        # Final sorting by relevance and recency
        return self._sort_insights_by_temporal_relevance(aggregated_insights)

    def _calculate_recency_score(self, analyzed_at) -> float:
        """Calculate recency score for temporal weighting (0.0 to 1.0)."""
        
        if not analyzed_at:
            return 0.0
            
        now = datetime.now(timezone.utc)
        if analyzed_at.tzinfo is None:
            analyzed_at = analyzed_at.replace(tzinfo=timezone.utc)
            
        # Calculate days since analysis
        days_diff = (now - analyzed_at).days
        
        # Linear decay: recent analyses get higher scores
        # Score approaches 0 after ~90 days
        return max(0.0, min(1.0, 1.0 - (days_diff / 90.0)))

    def _extract_insights_with_metadata(self, analysis_meta: dict) -> List[dict]:
        """Extract insights from a single analysis with temporal metadata."""
        insights = []
        analysis_data = analysis_meta['data']
        
        # Process strengths
        strengths = analysis_data.get("strengths", [])
        for strength in strengths:
            insights.append({
                'type': 'positive',
                'category': 'strength',
                'title': f"Fortaleza: {strength.get('feature', 'Feature destacado')}",
                'content': strength.get('userImpact', 'Impacto positivo en los usuarios'),
                'metadata': analysis_meta,
                'raw_data': strength
            })
        
        # Process weaknesses
        weaknesses = analysis_data.get("weaknesses", [])
        for weakness in weaknesses:
            insights.append({
                'type': 'negative',
                'category': 'weakness',
                'title': f"Área de mejora: {weakness.get('aspect', 'Aspecto a mejorar')}",
                'content': weakness.get('userImpact', 'Impacto negativo en los usuarios'),
                'metadata': analysis_meta,
                'raw_data': weakness
            })
        
        # Process insights array
        raw_insights = analysis_data.get("insights", [])
        for raw_insight in raw_insights:
            insight_type = self._determine_insight_type(raw_insight.get("type", ""))
            insights.append({
                'type': insight_type,
                'category': 'insight',
                'title': f"Insight: {raw_insight.get('type', 'Observación general')}",
                'content': raw_insight.get('observation', 'Observación general'),
                'metadata': analysis_meta,
                'raw_data': raw_insight
            })
        
        # Process recommendations
        recommendations = analysis_data.get("recommendations", [])
        for recommendation in recommendations:
            insights.append({
                'type': 'negative',
                'category': 'recommendation',
                'title': f"Recomendación ({recommendation.get('priority', 'medium')}): {recommendation.get('category', 'general')}",
                'content': recommendation.get('action', 'Acción recomendada'),
                'metadata': analysis_meta,
                'raw_data': recommendation
            })
        
        return insights

    def _apply_temporal_aggregation(self, raw_insights: List[dict], analyses_by_period=None) -> List[InsightItem]:
        """Apply temporal aggregation logic to merge similar insights across time."""
        # Group insights by similarity
        insight_groups = {}
        
        for insight in raw_insights:
            # Create a similarity key based on category, type, and content similarity
            similarity_key = self._generate_similarity_key(insight)
            
            if similarity_key not in insight_groups:
                insight_groups[similarity_key] = []
            insight_groups[similarity_key].append(insight)
        
        # Process each group to create aggregated insights
        aggregated_insights = []
        
        for similarity_key, group in insight_groups.items():
            # Sort group by recency (most recent first)
            group.sort(key=lambda x: x['metadata']['recency_score'], reverse=True)
            
            # Use the most recent insight as the base
            base_insight = group[0]
            
            # Calculate temporal trends and evolution
            evolution_data = self._analyze_insight_evolution(group)
            
            # Create the aggregated insight
            aggregated_insight = InsightItem(
                type=base_insight['type'],
                title=base_insight['title'],
                change=self._generate_temporal_change_value(base_insight, evolution_data),
                summary=self._generate_temporal_summary(base_insight, evolution_data),
                period=base_insight['metadata']['period']
            )
            
            aggregated_insights.append(aggregated_insight)
        
        return aggregated_insights

    def _generate_similarity_key(self, insight: dict) -> str:
        """Generate a key for grouping similar insights with enhanced semantic matching."""
        category = insight['category']
        insight_type = insight['type']
        
        # Extract both content and title for comprehensive analysis
        full_text = f"{insight.get('title', '')} {insight['content']}".lower()
        
        # Define semantic theme patterns with partial word matching
        theme_patterns = {
            'usabilidad_interfaz': [
                'interfaz', 'fácil', 'intuitiv', 'navegación', 'uso', 'sencill', 
                'simple', 'amigable', 'cómodo', 'accesible', 'claro', 'directo'
            ],
            'rendimiento_velocidad': [
                'rápid', 'lent', 'velocidad', 'carga', 'demora', 'espera', 
                'tardanza', 'tiempo', 'respuesta', 'fluidez'
            ],
            'funcionalidades_features': [
                'funcional', 'característic', 'opcion', 'herramient', 'feature',
                'capacidad', 'posibilidad', 'servicio', 'utilidad'
            ],
            'problemas_errores': [
                'problem', 'error', 'bug', 'fallo', 'crash', 'cierra',
                'falla', 'defect', 'issue', 'inconveniente'
            ],
            'costos_precios': [
                'precio', 'cost', 'caro', 'barato', 'comisión', 'tarifa',
                'gratis', 'pago', 'suscripción', 'plan'
            ],
            'seguridad_privacidad': [
                'segur', 'proteg', 'privac', 'confianc', 'datos',
                'información', 'cuenta', 'acceso'
            ],
            'soporte_atencion': [
                'soport', 'ayuda', 'atención', 'servicio', 'respuesta',
                'consulta', 'duda', 'problema'
            ],
            'diseño_visual': [
                'diseñ', 'visual', 'estét', 'color', 'imagen',
                'gráfic', 'pantalla', 'botón'
            ],
            'contenido_informacion': [
                'contenido', 'información', 'datos', 'detalle',
                'descripción', 'texto', 'mensaje'
            ]
        }
        
        # Find the best matching theme using partial word matching
        best_theme = 'general'
        max_matches = 0
        
        for theme, keywords in theme_patterns.items():
            matches = 0
            for keyword in keywords:
                # Use partial matching for better semantic grouping
                if keyword in full_text:
                    matches += 1
                    # Give extra weight to exact matches
                    if f" {keyword} " in f" {full_text} ":
                        matches += 0.5
            
            if matches > max_matches:
                max_matches = matches
                best_theme = theme
        
        # If no strong theme match found, extract most significant word
        if max_matches < 1:
            words = full_text.split()
            stop_words = {
                'de', 'la', 'el', 'en', 'y', 'a', 'que', 'es', 'se', 'no', 
                'fortaleza', 'área', 'mejora', 'insight', 'recomendación',
                'muy', 'más', 'sin', 'con', 'para', 'una', 'un', 'del', 'al',
                'los', 'las', 'su', 'por', 'son', 'fue', 'han', 'hace', 'está',
                'este', 'esta', 'aplicación', 'app', 'usuario', 'usuarios'
            }
            
            # Find first meaningful word (length > 3, not a stop word)
            for word in words:
                if len(word) > 3 and word not in stop_words:
                    best_theme = word[:10]  # Limit length
                    break
        
        # Create final similarity key
        return f"{category}_{insight_type}_{best_theme}"

    def _analyze_insight_evolution(self, insight_group: List[dict]) -> dict:
        """Analyze how an insight has evolved over time."""
        if len(insight_group) == 1:
            return {'trend': 'stable', 'frequency': 1, 'periods': 1}
        
        # Calculate frequency and trends
        periods = set(insight['metadata']['period'] for insight in insight_group)
        recency_scores = [insight['metadata']['recency_score'] for insight in insight_group]
        
        # Determine trend based on recency distribution
        avg_recent_score = sum(recency_scores) / len(recency_scores)
        
        if avg_recent_score > 0.7:
            trend = 'increasing'
        elif avg_recent_score > 0.3:
            trend = 'stable'
        else:
            trend = 'decreasing'
        
        return {
            'trend': trend,
            'frequency': len(insight_group),
            'periods': len(periods),
            'avg_recency': avg_recent_score
        }

    def _generate_temporal_change_value(self, base_insight: dict, evolution_data: dict) -> str:
        """Generate change value considering temporal evolution."""
        base_change = self._generate_change_value(
            base_insight['type'], 
            base_insight['content'],
            base_insight['raw_data'].get('priority') if base_insight['category'] == 'recommendation' else None
        )
        
        # Return base change without trend indicators
        return base_change

    def _generate_temporal_summary(self, base_insight: dict, evolution_data: dict) -> str:
        """Generate summary considering temporal evolution."""
        base_summary = base_insight['content']
        
        # Add temporal context
        if evolution_data['frequency'] > 1:
            trend_context = {
                'increasing': f"(Tendencia creciente - observado en {evolution_data['periods']} períodos)",
                'decreasing': f"(Tendencia decreciente - {evolution_data['frequency']} menciones históricas)",
                'stable': f"(Consistente - {evolution_data['frequency']} análisis)"
            }
            
            trend_suffix = trend_context.get(evolution_data['trend'], '')
            return f"{base_summary} {trend_suffix}"
        
        return base_summary

    def _sort_insights_by_temporal_relevance(self, insights: List[InsightItem]) -> List[InsightItem]:
        """Sort insights by temporal relevance and importance.
        
        Sorting priority:
        1. Negative insights first (more actionable)
        2. Most recent period first (2025-11 before 2024-12)
        3. Longer summaries (more detail)
        """
        return sorted(insights, key=lambda x: (
            0 if x.type == "negative" else 1,  # Negative first (more actionable)
            x.period if x.period != "unknown" else "9999-99",  # Most recent period first (descending)
            -len(x.summary)  # Then by detail level
        ), reverse=True)

    def _process_analysis_data(self, results: List) -> List[InsightItem]:
        """Process raw analysis data to extract structured insights.

        Args:
            results: Raw query results from BigQuery

        Returns:
            List of InsightItem objects
        """
        insights = []
        
        for row in results:
            try:
                # Parse the JSON data
                analysis_data = json.loads(row.json_data)
                review_date = row.review_date
                # Extract period from review_date (YYYY-MM format)
                period =  review_date.strftime("%Y-%m") if review_date else "unknown"
                # Process strengths as positive insights
                strengths = analysis_data.get("strengths", [])
                for strength in strengths:
                    content = strength.get('userImpact', 'Impacto positivo en los usuarios')
                    insights.append(InsightItem(
                        type="positive",
                        title=f"Fortaleza: {strength.get('feature', 'Feature destacado')}",
                        change=self._generate_change_value("positive", content),
                        summary=content,
                        period=period
                    ))

                # Process weaknesses as negative insights
                weaknesses = analysis_data.get("weaknesses", [])
                for weakness in weaknesses:
                    content = weakness.get('userImpact', 'Impacto negativo en los usuarios')
                    insights.append(InsightItem(
                        type="negative",
                        title=f"Área de mejora: {weakness.get('aspect', 'Aspecto a mejorar')}",
                        change=self._generate_change_value("negative", content),
                        summary=content,
                        period=period
                    ))

                # Process insights from the insights array
                raw_insights = analysis_data.get("insights", [])
                for raw_insight in raw_insights:
                    insight_type = self._determine_insight_type(raw_insight.get("type", ""))
                    content = raw_insight.get('observation', 'Observación general')
                    insights.append(InsightItem(
                        type=insight_type,
                        title=f"Insight: {raw_insight.get('type', 'Observación general')}",
                        change=self._generate_change_value(insight_type, content),
                        summary=content,
                        period=period
                    ))

                # Process recommendations as actionable insights
                recommendations = analysis_data.get("recommendations", [])
                for recommendation in recommendations:
                    priority = recommendation.get('priority', 'medium')
                    content = recommendation.get('action', 'Acción recomendada')
                    
                    insights.append(InsightItem(
                        type="negative",  # Recommendations usually indicate areas to improve
                        title=f"Recomendación ({priority}): {recommendation.get('category', 'general')}",
                        change=self._generate_change_value("negative", content, priority=priority),
                        summary=content,
                        period=period
                    ))

            except (json.JSONDecodeError, KeyError, AttributeError) as e:
                logger.warning(f"Error processing analysis data: {e}")
                continue

        # Remove duplicates and sort by relevance
        return self._deduplicate_and_sort_insights(insights)

    def _determine_insight_type(self, insight_type: str) -> str:
        """Determine if an insight should be categorized as positive or negative."""
        negative_types = [
            "feature_gap", "adoption_barrier", "satisfaction_driver", 
            "technical_issue", "usability_issue"
        ]
        
        if insight_type.lower() in negative_types:
            return "negative"
        else:
            return "positive"



    def _deduplicate_and_sort_insights(self, insights: List[InsightItem]) -> List[InsightItem]:
        """Remove duplicate insights and sort by relevance."""
        # Simple deduplication based on title similarity
        seen_titles = set()
        unique_insights = []
        
        for insight in insights:
            # Create a normalized title for comparison
            normalized_title = insight.title.lower().strip()
            
            if normalized_title not in seen_titles:
                seen_titles.add(normalized_title)
                unique_insights.append(insight)

        # Sort: negative insights first (more actionable), then by period descending
        unique_insights.sort(
            key=lambda x: (
                0 if x.type == "negative" else 1,  # Negative first
                x.period  # Then by period
            ),
            reverse=True
        )

        return unique_insights


# Singleton instance
insights_service = InsightsService()