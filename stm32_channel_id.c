/* ========================================================================
   CODE STM32 - Ajout ID de canal pour robustesse
   ======================================================================== */

// USER CODE BEGIN Includes
#include <stdio.h>
#include <string.h>
#include <math.h>
#include <stdint.h>
// USER CODE END Includes

// USER CODE BEGIN PV

// Structure pour envoyer ID + valeur par canal
typedef struct {
    uint8_t channel_id;  // 0-5 pour identifier le canal
    int16_t value;       // Valeur filtrée
} __attribute__((packed)) channel_sample_t;

// Variables pour le filtre passe-haut (1er ordre)
#define ALPHA 0.997f

// Buffer DMA pour ADC (6 canaux)
uint16_t adc_buffer[6];

// Buffer de valeur post filtrée passe haut
int16_t valeurs_filtrees[6];

// Flag de fin d'acquisition
volatile uint32_t conversion_complete = 0;
uint32_t last_processed = 0;

// USER CODE END PV


// ============================================================================
// DANS LA BOUCLE PRINCIPALE (main.c)
// ============================================================================

int main(void)
{
    /* ... Initialisation HAL, GPIO, DMA, ADC, UART, TIM ... */

    /* USER CODE BEGIN 2 */

    /* Calibration de l'ADC */
    HAL_ADCEx_Calibration_Start(&hadc1, ADC_SINGLE_ENDED);

    // IMPORTANT: Démarrer le Timer AVANT le DMA pour meilleure sync
    HAL_TIM_Base_Start(&htim2);
    HAL_Delay(10);  // Attendre stabilisation

    // PUIS démarrer le DMA
    HAL_ADC_Start_DMA(&hadc1, (uint32_t*)adc_buffer, 6);

    /* USER CODE END 2 */

    /* Infinite loop */
    /* USER CODE BEGIN WHILE */

    // Variables de filtre
    float hp_prev[6] = {0};
    float input_prev[6] = {0};

    while (1)
    {
        //----------------------------------------------------------- ACQUISITION
        // Attente du callback de conversion
        while(conversion_complete == last_processed);
        last_processed = conversion_complete;

        //----------------------------------------------------------- TRAITEMENT
        // Filtrer les 6 canaux
        for(int i = 0; i < 6; i++) {
            float input = (float)adc_buffer[i];

            // Filtre passe-haut
            float output = ALPHA * (hp_prev[i] + input - input_prev[i]);

            // Sauvegarder pour prochaine itération
            hp_prev[i] = output;
            input_prev[i] = input;

            // Convertir en int16_t
            valeurs_filtrees[i] = (int16_t)output;
        }

        //----------------------------------------------------------- ENVOI UART
        // ✅ NOUVEAU FORMAT : ID + valeur par canal (18 bytes au lieu de 12)
        channel_sample_t samples[6];

        for(int i = 0; i < 6; i++) {
            samples[i].channel_id = i;  // ← ID pour identifier le canal
            samples[i].value = valeurs_filtrees[i];
        }

        // Envoyer les 6 échantillons (18 bytes total)
        HAL_UART_Transmit(&huart2, (uint8_t*)samples, sizeof(samples), 1);

    /* USER CODE END WHILE */

    /* USER CODE BEGIN 3 */
    }
  /* USER CODE END 3 */
}


// ============================================================================
// CALLBACK ADC (inchangé)
// ============================================================================

/* USER CODE BEGIN 4 */
volatile uint32_t callback_count = 0;

void HAL_ADC_ConvCpltCallback(ADC_HandleTypeDef* hadc)
{
    if(hadc->Instance == ADC1)
    {
        conversion_complete++;
        callback_count++;
    }
}
/* USER CODE END 4 */


/* ========================================================================
   RÉSUMÉ DES CHANGEMENTS :
   ========================================================================

   1. Ajouter typedef struct channel_sample_t avec __attribute__((packed))
   2. Dans la boucle, créer un tableau channel_sample_t samples[6]
   3. Remplir samples[i].channel_id = i
   4. Remplir samples[i].value = valeurs_filtrees[i]
   5. Envoyer sizeof(samples) = 18 bytes

   AVANTAGES :
   - Plus de problème d'ordre aléatoire au redémarrage
   - Détection automatique des erreurs de synchronisation
   - Protocole robuste même avec pertes de paquets

   ======================================================================== */
