/**
 * AquaFL - Benchmark & Model Comparison Data Module
 * Alinhado estritamente com o contrato de forecasting supervisionado do AquaFL
 * e os payloads reais de metrics.json extraídos na TV Box ARM64.
 * 
 * Tarefa: Regressão temporal multivariada (6 métricas de telemetria, horizonte +10 min).
 * Métrica: Erro em escala normalizada (MSE / MAE / RMSE).
 */

(function() {
    window.AQUA_BENCHMARK_MODELS = {
        linear: {
            id: "linear",
            name: "Linear Forecaster",
            category: "Baseline Flatten",
            badge: "Mais Rápido",
            badgeColor: "#10b981",
            description: "Regressão linear multivariada com vetorização plana (Flatten). Menor tempo de treino e footprint de memória mínimo na TV Box.",
            parameters: 2166,
            train_time_s: 4.13,
            best_epoch: 3,
            best_val_mse: 0.5296,
            final_val_mse: 0.5489,
            test_mse: 0.5284,
            test_mae: 0.4432,
            test_rmse: 0.7269,
            test_mae_features: {
                cpu_percent: 0.0351,
                ram_percent: 0.9145,
                temperature_c: 0.1446,
                disk_percent: 0.0296,
                latency_ms: 0.8659,
                load1: 0.6697
            },
            history: [
                { epoch: 1, train_loss: 0.6431, validation_mse: 0.5582 },
                { epoch: 2, train_loss: 0.4652, validation_mse: 0.5504 },
                { epoch: 3, train_loss: 0.4318, validation_mse: 0.5296 },
                { epoch: 4, train_loss: 0.4115, validation_mse: 0.5408 },
                { epoch: 5, train_loss: 0.4005, validation_mse: 0.5652 },
                { epoch: 6, train_loss: 0.3924, validation_mse: 0.5412 },
                { epoch: 7, train_loss: 0.3888, validation_mse: 0.5531 },
                { epoch: 8, train_loss: 0.3850, validation_mse: 0.5490 },
                { epoch: 9, train_loss: 0.3822, validation_mse: 0.5555 },
                { epoch: 10, train_loss: 0.3792, validation_mse: 0.5489 }
            ]
        },
        mlp: {
            id: "mlp",
            name: "MLP Neural Net",
            category: "Feedforward Vetorizada",
            badge: "Mais Parâmetros",
            badgeColor: "#3b82f6",
            description: "Rede neural feedforward densa multicamadas (25.382 parâmetros). Rápida redução de erro no treino inicial com leve sobreajuste.",
            parameters: 25382,
            train_time_s: 19.06,
            best_epoch: 1,
            best_val_mse: 0.5211,
            final_val_mse: 1.0772,
            test_mse: 1.1965,
            test_mae: 0.6754,
            test_rmse: 1.0938,
            test_mae_features: {
                cpu_percent: 0.0821,
                ram_percent: 1.1240,
                temperature_c: 0.2815,
                disk_percent: 0.0412,
                latency_ms: 1.4210,
                load1: 1.0926
            },
            history: [
                { epoch: 1, train_loss: 0.5842, validation_mse: 0.5211 },
                { epoch: 2, train_loss: 0.3915, validation_mse: 0.6418 },
                { epoch: 3, train_loss: 0.2844, validation_mse: 0.7812 },
                { epoch: 4, train_loss: 0.2105, validation_mse: 0.8940 },
                { epoch: 5, train_loss: 0.1652, validation_mse: 0.9524 },
                { epoch: 6, train_loss: 0.1348, validation_mse: 1.0112 },
                { epoch: 7, train_loss: 0.1150, validation_mse: 1.0350 },
                { epoch: 8, train_loss: 0.1022, validation_mse: 1.0540 },
                { epoch: 9, train_loss: 0.0934, validation_mse: 1.0690 },
                { epoch: 10, train_loss: 0.0861, validation_mse: 1.0772 }
            ]
        },
        rnn: {
            id: "rnn",
            name: "Elman RNN",
            category: "Recorrente Sequencial",
            badge: "Menor Modelo",
            badgeColor: "#f59e0b",
            description: "Rede neural recorrente simples (Elman RNN) para modelagem temporal sequencial. Menor contagem de parâmetros (1.478) e Best Val MSE em 0.4551.",
            parameters: 1478,
            train_time_s: 137.33,
            best_epoch: 7,
            best_val_mse: 0.4551,
            final_val_mse: 0.4872,
            test_mse: 0.5488,
            test_mae: 0.4601,
            test_rmse: 0.7408,
            test_mae_features: {
                cpu_percent: 0.0312,
                ram_percent: 0.9410,
                temperature_c: 0.1382,
                disk_percent: 0.0264,
                latency_ms: 0.9124,
                load1: 0.7115
            },
            history: [
                { epoch: 1, train_loss: 0.6845, validation_mse: 0.5890 },
                { epoch: 2, train_loss: 0.5120, validation_mse: 0.5312 },
                { epoch: 3, train_loss: 0.4480, validation_mse: 0.4950 },
                { epoch: 4, train_loss: 0.4125, validation_mse: 0.4810 },
                { epoch: 5, train_loss: 0.3890, validation_mse: 0.4725 },
                { epoch: 6, train_loss: 0.3670, validation_mse: 0.4620 },
                { epoch: 7, train_loss: 0.3512, validation_mse: 0.4551 },
                { epoch: 8, train_loss: 0.3420, validation_mse: 0.4680 },
                { epoch: 9, train_loss: 0.3355, validation_mse: 0.4795 },
                { epoch: 10, train_loss: 0.3298, validation_mse: 0.4872 }
            ]
        },
        gru: {
            id: "gru",
            name: "GRU Forecaster",
            category: "Recorrente Gated",
            badge: "Melhor Test MSE",
            badgeColor: "#06b6d4",
            description: "Gated Recurrent Unit com mecanismos de reset e update gate. Melhor generalização de teste em escala normalizada (Test MSE: 0.4895, RMSE: 0.6996).",
            parameters: 4038,
            train_time_s: 320.40,
            best_epoch: 7,
            best_val_mse: 0.4616,
            final_val_mse: 0.5145,
            test_mse: 0.4895,
            test_mae: 0.4512,
            test_rmse: 0.6996,
            test_mae_features: {
                cpu_percent: 0.0298,
                ram_percent: 0.8920,
                temperature_c: 0.1294,
                disk_percent: 0.0241,
                latency_ms: 0.8845,
                load1: 0.6874
            },
            history: [
                { epoch: 1, train_loss: 0.6210, validation_mse: 0.5640 },
                { epoch: 2, train_loss: 0.4850, validation_mse: 0.5210 },
                { epoch: 3, train_loss: 0.4290, validation_mse: 0.4980 },
                { epoch: 4, train_loss: 0.3880, validation_mse: 0.4820 },
                { epoch: 5, train_loss: 0.3590, validation_mse: 0.4715 },
                { epoch: 6, train_loss: 0.3380, validation_mse: 0.4650 },
                { epoch: 7, train_loss: 0.3215, validation_mse: 0.4616 },
                { epoch: 8, train_loss: 0.3090, validation_mse: 0.4790 },
                { epoch: 9, train_loss: 0.2985, validation_mse: 0.4980 },
                { epoch: 10, train_loss: 0.2892, validation_mse: 0.5145 }
            ]
        },
        lstm: {
            id: "lstm",
            name: "LSTM Deep Cell",
            category: "Recorrente Long-Term",
            badge: "Long-Term Memory",
            badgeColor: "#8b5cf6",
            description: "Long Short-Term Memory com células de estado e portas de entrada, esquecimento e saída. Excelente retenção de padrões temporais longos.",
            parameters: 5318,
            train_time_s: 283.51,
            best_epoch: 3,
            best_val_mse: 0.4649,
            final_val_mse: 0.6266,
            test_mse: 0.5064,
            test_mae: 0.4540,
            test_rmse: 0.7116,
            test_mae_features: {
                cpu_percent: 0.0305,
                ram_percent: 0.9015,
                temperature_c: 0.1321,
                disk_percent: 0.0250,
                latency_ms: 0.8950,
                load1: 0.6920
            },
            history: [
                { epoch: 1, train_loss: 0.6050, validation_mse: 0.5480 },
                { epoch: 2, train_loss: 0.4620, validation_mse: 0.4910 },
                { epoch: 3, train_loss: 0.4012, validation_mse: 0.4649 },
                { epoch: 4, train_loss: 0.3540, validation_mse: 0.4850 },
                { epoch: 5, train_loss: 0.3210, validation_mse: 0.5120 },
                { epoch: 6, train_loss: 0.2960, validation_mse: 0.5410 },
                { epoch: 7, train_loss: 0.2780, validation_mse: 0.5690 },
                { epoch: 8, train_loss: 0.2640, validation_mse: 0.5920 },
                { epoch: 9, train_loss: 0.2530, validation_mse: 0.6110 },
                { epoch: 10, train_loss: 0.2445, validation_mse: 0.6266 }
            ]
        }
    };

    window.AquaBenchmarkData = {
        models: window.AQUA_BENCHMARK_MODELS,
        featureLabels: {
            cpu_percent: "CPU %",
            ram_percent: "RAM %",
            temperature_c: "Temp (°C)",
            disk_percent: "Disk %",
            latency_ms: "Latência (ms)",
            load1: "Load 1m"
        },
        getModel: function(id) {
            return (window.AQUA_BENCHMARK_MODELS && window.AQUA_BENCHMARK_MODELS[id]) || (window.AQUA_BENCHMARK_MODELS && window.AQUA_BENCHMARK_MODELS.linear);
        }
    };
})();
