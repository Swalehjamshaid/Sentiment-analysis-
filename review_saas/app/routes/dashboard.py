{% extends "base.html" %}

{% block title %}BizChat • Review Dashboard{% endblock %}

{% block extra_head %}
<style>
    .metric-card {
        background: rgba(30, 41, 59, 0.4);
        backdrop-filter: blur(8px);
        border: 1px solid rgba(255, 255, 255, 0.05);
    }
    input[type="date"]::-webkit-calendar-picker-indicator { filter: invert(1); cursor: pointer; }
</style>
{% endblock %}

{% block content %}
<div class="space-y-8" x-data="{
    selectedCompany: { 
        id: '{{ selected_company.id if selected_company else '' }}', 
        name: '{{ selected_company.name if selected_company else 'Global Overview' }}' 
    },
    syncing: false,
    dateStart: '{{ dashboard_payload.date_range.start if dashboard_payload else '' }}',
    dateEnd: '{{ dashboard_payload.date_range.end if dashboard_payload else '' }}',
    currentPage: 1,
    pageSize: 10,
    dashboardData: {{ dashboard_payload | tojson | safe if dashboard_payload else '{}' }},
    
    get paginatedReviews() {
        if (!this.dashboardData.reviews?.data) return [];
        let start = (this.currentPage - 1) * this.pageSize;
        return this.dashboardData.reviews.data.slice(start, start + this.pageSize);
    },
    get totalPages() {
        return Math.ceil((this.dashboardData.reviews?.total || 0) / this.pageSize);
    },
    applyFilter() {
        window.location.href = `/dashboard?company_id=${this.selectedCompany.id}&start=${this.dateStart}&end=${this.dateEnd}`;
    },
    async triggerSync() {
        if (!this.selectedCompany.id) return;
        this.syncing = true;
        try {
            const response = await fetch(`/api/companies/${this.selectedCompany.id}/sync`, { method: 'POST' });
            if (response.ok) {
                // Wait 2 seconds for background task to start, then refresh
                setTimeout(() => { 
                    this.syncing = false; 
                    window.location.reload(); 
                }, 2000);
            }
        } catch (e) {
            console.error('Sync failed', e);
            this.syncing = false;
        }
    }
}">

    <div class="flex flex-col lg:flex-row justify-between items-start lg:items-center gap-6">
        <div>
            <h1 class="text-4xl font-extrabold tracking-tight text-white">
                <span class="bg-gradient-to-r from-brand-400 to-indigo-400 bg-clip-text text-transparent" x-text="selectedCompany.name"></span>
            </h1>
            {% if selected_company %}
            <p class="text-slate-500 text-xs mt-1 uppercase tracking-widest">
                Last Synced: {{ selected_company.last_synced_at.strftime('%Y-%m-%d %H:%M') if selected_company.last_synced_at else 'Never' }}
            </p>
            {% endif %}
        </div>

        <div class="flex flex-col sm:flex-row gap-3 w-full lg:w-auto">
            <button @click="triggerSync()" 
                    :disabled="syncing || !selectedCompany.id"
                    class="flex items-center gap-2 px-4 py-3 bg-brand-600/10 border border-brand-500/20 rounded-xl hover:bg-brand-600 hover:text-white transition-all text-sm font-bold text-brand-400 disabled:opacity-50">
                <i class="fas fa-sync-alt" :class="syncing ? 'fa-spin' : ''"></i>
                <span x-text="syncing ? 'Fetching...' : 'Sync Now'"></span>
            </button>

            <div class="relative" x-data="{ open: false }">
                <button @click="open = !open" class="w-full sm:w-64 flex justify-between items-center px-4 py-3 bg-slate-900/50 border border-slate-700 rounded-xl hover:border-brand-500 transition-all text-sm font-medium">
                    <span class="flex items-center gap-2"><i class="fas fa-building text-brand-500"></i><span x-text="selectedCompany.name"></span></span>
                    <i class="fas fa-chevron-down text-xs transition-transform" :class="open ? 'rotate-180' : ''"></i>
                </button>
                <div x-show="open" @click.away="open = false" x-cloak class="absolute right-0 w-full mt-2 bg-slate-900 border border-slate-800 rounded-xl shadow-2xl z-50 overflow-hidden">
                    <div class="max-h-60 overflow-y-auto">
                        <a href="/dashboard" class="block px-4 py-3 hover:bg-brand-600/10 text-sm border-b border-slate-800/50 text-slate-300">Global Overview</a>
                        {% for company in companies %}
                        <div class="px-4 py-3 hover:bg-brand-600/10 cursor-pointer text-sm border-b border-slate-800/50 text-slate-300" 
                             @click="selectedCompany = {id: '{{ company.id }}', name: '{{ company.name }}'}; open = false; applyFilter()">
                            {{ company.name }}
                        </div>
                        {% endfor %}
                    </div>
                </div>
            </div>
        </div>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <div class="metric-card p-6 rounded-2xl">
            <p class="text-slate-500 text-[10px] font-bold uppercase tracking-widest">Total Reviews</p>
            <p class="text-3xl font-bold mt-1 text-white" x-text="dashboardData.metrics.total || 0"></p>
        </div>
        <div class="metric-card p-6 rounded-2xl">
            <p class="text-slate-500 text-[10px] font-bold uppercase tracking-widest">Avg Rating</p>
            <p class="text-3xl font-bold mt-1 text-amber-400"><span x-text="dashboardData.metrics.avg_rating || '0'"></span><span class="text-slate-600 text-sm ml-1">★</span></p>
        </div>
        <div class="metric-card p-6 rounded-2xl">
            <p class="text-slate-500 text-[10px] font-bold uppercase tracking-widest">Risk Analysis</p>
            <p class="text-3xl font-bold mt-1" :class="dashboardData.metrics.risk_level === 'High' ? 'text-rose-500' : 'text-emerald-500'" x-text="dashboardData.metrics.risk_level || 'Safe'"></p>
        </div>
        <div class="metric-card p-6 rounded-2xl">
            <p class="text-slate-500 text-[10px] font-bold uppercase tracking-widest">Trend</p>
            <p class="text-2xl font-bold mt-1 text-white capitalize" x-text="dashboardData.trend.signal || 'Stable'"></p>
        </div>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div class="metric-card p-6 rounded-2xl">
            <h3 class="font-bold text-sm mb-6 text-slate-400 uppercase tracking-widest">Activity Heatmap</h3>
            <div class="h-[250px]"><canvas id="heatmapChart"></canvas></div>
        </div>
        <div class="metric-card p-6 rounded-2xl">
            <h3 class="font-bold text-sm mb-6 text-slate-400 uppercase tracking-widest">Sentiment Mix</h3>
            <div class="h-[250px]"><canvas id="sentimentChart"></canvas></div>
        </div>
    </div>

    <div class="metric-card rounded-2xl overflow-hidden border border-slate-800">
        <div class="overflow-x-auto">
            <table class="w-full text-sm text-left">
                <thead class="bg-slate-900/80 text-slate-500 uppercase text-[10px] font-bold">
                    <tr>
                        <th class="px-6 py-4">Reviewer</th>
                        <th class="px-6 py-4">Rating</th>
                        <th class="px-6 py-4">Sentiment</th>
                        <th class="px-6 py-4">Comment Snippet</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-slate-800">
                    <template x-for="review in paginatedReviews" :key="review.id">
                        <tr class="hover:bg-white/5 transition-colors">
                            <td class="px-6 py-4 font-semibold text-slate-200" x-text="review.reviewer_name"></td>
                            <td class="px-6 py-4 text-amber-400 font-bold" x-text="review.rating + ' ★'"></td>
                            <td class="px-6 py-4">
                                <span class="px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-widest" 
                                      :class="review.sentiment_category === 'Positive' ? 'bg-emerald-500/10 text-emerald-500' : 'bg-rose-500/10 text-rose-500'"
                                      x-text="review.sentiment_category"></span>
                            </td>
                            <td class="px-6 py-4 text-slate-500 max-w-sm truncate" x-text="review.text"></td>
                        </tr>
                    </template>
                </tbody>
            </table>
        </div>
    </div>
</div>
{% endblock %}

{% block extra_js %}
<script>
document.addEventListener('DOMContentLoaded', () => {
    const data = {{ dashboard_payload | tojson | safe if dashboard_payload else 'null' }};
    if (!data) return;

    Chart.defaults.color = '#64748b';
    Chart.defaults.font.family = 'Inter';

    // Heatmap Chart
    new Chart(document.getElementById('heatmapChart'), {
        type: 'bar',
        data: {
            labels: data.heatmap.labels.map(h => `${h}:00`),
            datasets: [{ data: data.heatmap.data, backgroundColor: '#8b5cf6', borderRadius: 4 }]
        },
        options: { maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { display: false }, x: { grid: { display: false } } } }
    });

    // Sentiment Chart
    new Chart(document.getElementById('sentimentChart'), {
        type: 'doughnut',
        data: {
            labels: ['Positive', 'Neutral', 'Negative'],
            datasets: [{
                data: [data.sentiment.Positive, data.sentiment.Neutral, data.sentiment.Negative],
                backgroundColor: ['#10b981', '#64748b', '#ef4444'],
                borderWidth: 0
            }]
        },
        options: { maintainAspectRatio: false, cutout: '80%', plugins: { legend: { position: 'bottom' } } }
    });
});
</script>
{% endblock %}
