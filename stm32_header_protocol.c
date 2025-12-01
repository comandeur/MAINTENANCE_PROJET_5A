/* ========================================================================
   CODE STM32 - Protocole avec header 0xAA pour synchronisation
   ======================================================================== */

// USER CODE BEGIN Includes
#include <stdio.h>
#include <string.h>
#include <math.h>
#include <stdint.h>
// USER CODE END Includes

// USER CODE BEGIN PV

// Variables pour le filtre passe-haut (1er ordre)
#define ALPHA 0.997f

// Buffer DMA pour ADC (6 canaux)
uint16_t adc_buffer[6];

// Buffer de valeur post filtrée passe haut
int16_t valeurs_filtrees[6];

// Buffer UART avec header
uint8_t uart_packet[13];  // 1 header + 12 bytes (6 × int16_t)

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

    // Démarrer le Timer
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
        // ✅ FORMAT: Header 0xAA + 6 × int16_t (13 bytes total)
        uart_packet[0] = 0xAA;  // Header pour synchronisation
        memcpy(&uart_packet[1], valeurs_filtrees, 12);  // Copier les 6 valeurs

        // Envoyer le paquet (13 bytes)
        HAL_UART_Transmit(&huart2, uart_packet, 13, 1);

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
   RÉSUMÉ DU PROTOCOLE :
   ========================================================================

   FORMAT: 13 bytes par échantillon
   - Byte 0:    0xAA (header pour synchronisation)
   - Bytes 1-2:  Canal A0 (int16_t little endian)
   - Bytes 3-4:  Canal A1 (int16_t little endian)
   - Bytes 5-6:  Canal A2 (int16_t little endian)
   - Bytes 7-8:  Canal A3 (int16_t little endian)
   - Bytes 9-10: Canal A4 (int16_t little endian)
   - Bytes 11-12: Canal A5 (int16_t little endian)

   AVANTAGES :
   - Header 0xAA permet la synchronisation
   - Simple et efficace (13 bytes vs 18 bytes avec channel_id)
   - Détection automatique des erreurs de synchronisation
   - Compatible avec baud rate élevé (921600)

   ======================================================================== */
