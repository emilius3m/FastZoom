<!-- templates/sites/components/_photo_edit_modal.html - EDITOR METADATI FOTO CON SCHEMA JSON -->
<div x-show="showEditModal"
     x-transition:enter="transition ease-out duration-300"
     x-transition:enter-start="opacity-0"
     x-transition:enter-end="opacity-100"
     x-transition:leave="transition ease-in duration-200"
     x-transition:leave-start="opacity-100"
     x-transition:leave-end="opacity-0"
     class="fixed inset-0 bg-gray-600 bg-opacity-75 overflow-y-auto h-full w-full z-50"
     @click.self="closeEditModal()">
    
    <div class="relative top-10 mx-auto p-5 border w-11/12 md:w-4/5 lg:w-3/4 xl:w-2/3 shadow-lg rounded-md bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 max-h-[90vh] overflow-y-auto">
        
        <!-- Header -->
        <div class="flex items-center justify-between mb-6 pb-4 border-b border-gray-200 dark:border-gray-700">
            <div>
                <h3 class="text-xl font-semibold text-gray-900 dark:text-white">
                    <span x-show="!isMultipleSelection">📸 Modifica Metadati Fotografici</span>
                    <span x-show="isMultipleSelection">📸 Modifica Metadati - Selezione Multipla</span>
                </h3>
                <p class="mt-1 text-sm text-gray-600 dark:text-gray-300">
                    <span x-show="!isMultipleSelection && selectedPhoto">
                        File: <span class="font-mono" x-text="selectedPhoto.original_filename || selectedPhoto.filename"></span>
                    </span>
                    <span x-show="isMultipleSelection" x-text="'Modifica ' + selectedPhotos.length + ' foto selezionate'"></span>
                </p>
            </div>
            <button @click="closeEditModal()"
                    class="text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300">
                <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                </svg>
            </button>
        </div>

        <!-- Alert -->
        <div x-show="alert.show" 
             x-transition
             :class="{
                 'bg-green-50 border-green-500 text-green-800': alert.type === 'success',
                 'bg-red-50 border-red-500 text-red-800': alert.type === 'error',
                 'bg-yellow-50 border-yellow-500 text-yellow-800': alert.type === 'warning'
             }"
             class="border-l-4 p-4 mb-6 rounded-r">
            <div class="flex items-center">
                <span x-text="alert.message"></span>
                <button @click="alert.show = false" class="ml-auto">✕</button>
            </div>
        </div>

        <!-- Form -->
        <form @submit.prevent="saveMetadata" class="space-y-6">
            
            <!-- INFORMAZIONI BASE -->
            <div class="bg-gray-50 dark:bg-gray-900 p-4 rounded-lg">
                <h4 class="font-semibold text-gray-900 dark:text-white mb-4 flex items-center">
                    <svg class="w-5 h-5 mr-2 text-blue-600" fill="currentColor" viewBox="0 0 20 20">
                        <path d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4z"></path>
                    </svg>
                    Informazioni Base
                </h4>
                
                <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <!-- Titolo -->
                    <div class="md:col-span-2">
                        <label class="block mb-2 text-sm font-medium text-gray-900 dark:text-white">
                            Titolo <span class="text-red-600">*</span>
                        </label>
                        <input type="text" 
                               x-model="metadata.title"
                               required
                               maxlength="250"
                               class="bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 text-gray-900 dark:text-white text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5"
                               placeholder="Titolo descrittivo della fotografia">
                    </div>

                    <!-- Descrizione -->
                    <div class="md:col-span-2">
                        <label class="block mb-2 text-sm font-medium text-gray-900 dark:text-white">
                            Descrizione <span class="text-red-600">*</span>
                        </label>
                        <textarea x-model="metadata.description"
                                  required
                                  rows="4"
                                  class="bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 text-gray-900 dark:text-white text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5"
                                  placeholder="Descrizione dettagliata del contenuto fotografico"></textarea>
                    </div>

                    <!-- Tipo Soggetto -->
                    <div>
                        <label class="block mb-2 text-sm font-medium text-gray-900 dark:text-white">
                            Tipo Soggetto <span class="text-red-600">*</span>
                        </label>
                        <select x-model="metadata.subject_type"
                                required
                                class="bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 text-gray-900 dark:text-white text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5">
                            <option value="">Seleziona...</option>
                            <option value="reperto">Reperto</option>
                            <option value="struttura">Struttura</option>
                            <option value="scavo">Scavo</option>
                            <option value="ambiente">Ambiente</option>
                            <option value="dettaglio">Dettaglio</option>
                            <option value="ricostruzione">Ricostruzione</option>
                        </select>
                    </div>

                    <!-- Visibilità -->
                    <div>
                        <label class="block mb-2 text-sm font-medium text-gray-900 dark:text-white">
                            Visibilità
                        </label>
                        <select x-model="metadata.visibility"
                                class="bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 text-gray-900 dark:text-white text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5">
                            <option value="public">Pubblica</option>
                            <option value="team">Solo Team</option>
                            <option value="private">Privata</option>
                        </select>
                    </div>
                </div>
            </div>

            <!-- CONTESTO ARCHEOLOGICO -->
            <div class="bg-gray-50 dark:bg-gray-900 p-4 rounded-lg">
                <h4 class="font-semibold text-gray-900 dark:text-white mb-4 flex items-center">
                    <svg class="w-5 h-5 mr-2 text-amber-600" fill="currentColor" viewBox="0 0 20 20">
                        <path d="M10.394 2.08a1 1 0 00-.788 0l-7 3a1 1 0 000 1.84L5.25 8.051a.999.999 0 01.356-.257l4-1.714a1 1 0 11.788 1.838L7.667 9.088l1.94.831a1 1 0 00.787 0l7-3a1 1 0 000-1.838l-7-3zM3.31 9.397L5 10.12v4.102a8.969 8.969 0 00-1.05-.174 1 1 0 01-.89-.89 11.115 11.115 0 01.25-3.762zM9.3 16.573A9.026 9.026 0 007 14.935v-3.957l1.818.78a3 3 0 002.364 0l5.508-2.361a11.026 11.026 0 01.25 3.762 1 1 0 01-.89.89 8.968 8.968 0 00-5.35 2.524 1 1 0 01-1.4 0zM6 18a1 1 0 001-1v-2.065a8.935 8.935 0 00-2-.712V17a1 1 0 001 1z"></path>
                    </svg>
                    Contesto Archeologico
                </h4>
                
                <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <!-- Contesto Archeologico -->
                    <div class="md:col-span-2">
                        <label class="block mb-2 text-sm font-medium text-gray-900 dark:text-white">
                            Contesto Archeologico
                        </label>
                        <textarea x-model="metadata.archaeological_context"
                                  rows="3"
                                  maxlength="500"
                                  class="bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 text-gray-900 dark:text-white text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5"
                                  placeholder="Descrizione contesto archeologico di rinvenimento"></textarea>
                    </div>

                    <!-- Cronologia -->
                    <div>
                        <label class="block mb-2 text-sm font-medium text-gray-900 dark:text-white">
                            Cronologia
                        </label>
                        <input type="text"
                               x-model="metadata.chronology"
                               class="bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 text-gray-900 dark:text-white text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5"
                               placeholder="Es: Età del Bronzo">
                    </div>

                    <!-- Unità Stratigrafica -->
                    <div>
                        <label class="block mb-2 text-sm font-medium text-gray-900 dark:text-white">
                            Unità Stratigrafica (US)
                        </label>
                        <input type="text"
                               x-model="metadata.stratigraphic_unit"
                               class="bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 text-gray-900 dark:text-white text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5"
                               placeholder="Es: US 1234">
                    </div>

                    <!-- Materiale -->
                    <div>
                        <label class="block mb-2 text-sm font-medium text-gray-900 dark:text-white">
                            Materiale
                        </label>
                        <select x-model="metadata.material"
                                class="bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 text-gray-900 dark:text-white text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5">
                            <option value="">Seleziona...</option>
                            <option value="ceramica">Ceramica</option>
                            <option value="metallo">Metallo</option>
                            <option value="pietra">Pietra</option>
                            <option value="vetro">Vetro</option>
                            <option value="osso">Osso</option>
                            <option value="altro">Altro</option>
                        </select>
                    </div>

                    <!-- Stato Conservazione -->
                    <div>
                        <label class="block mb-2 text-sm font-medium text-gray-900 dark:text-white">
                            Stato di Conservazione
                        </label>
                        <select x-model="metadata.conservation_state"
                                class="bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 text-gray-900 dark:text-white text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5">
                            <option value="">Seleziona...</option>
                            <option value="ottimo">Ottimo</option>
                            <option value="buono">Buono</option>
                            <option value="discreto">Discreto</option>
                            <option value="mediocre">Mediocre</option>
                            <option value="cattivo">Cattivo</option>
                        </select>
                    </div>
                </div>
            </div>

            <!-- LOCALIZZAZIONE -->
            <div class="bg-gray-50 dark:bg-gray-900 p-4 rounded-lg">
                <h4 class="font-semibold text-gray-900 dark:text-white mb-4 flex items-center">
                    <svg class="w-5 h-5 mr-2 text-green-600" fill="currentColor" viewBox="0 0 20 20">
                        <path fill-rule="evenodd" d="M5.05 4.05a7 7 0 119.9 9.9L10 18.9l-4.95-4.95a7 7 0 010-9.9zM10 11a2 2 0 100-4 2 2 0 000 4z" clip-rule="evenodd"></path>
                    </svg>
                    Localizzazione
                </h4>
                
                <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div>
                        <label class="block mb-2 text-sm font-medium text-gray-900 dark:text-white">Area</label>
                        <input type="text"
                               x-model="metadata.location.area"
                               class="bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 text-gray-900 dark:text-white text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5">
                    </div>
                    <div>
                        <label class="block mb-2 text-sm font-medium text-gray-900 dark:text-white">Settore</label>
                        <input type="text"
                               x-model="metadata.location.sector"
                               class="bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 text-gray-900 dark:text-white text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5">
                    </div>
                    <div>
                        <label class="block mb-2 text-sm font-medium text-gray-900 dark:text-white">Coordinate</label>
                        <input type="text"
                               x-model="metadata.location.coordinates"
                               class="bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 text-gray-900 dark:text-white text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5"
                               placeholder="Es: 41.9028, 12.4964">
                    </div>
                </div>
            </div>

            <!-- DATI TECNICI RIPRESA -->
            <div class="bg-gray-50 dark:bg-gray-900 p-4 rounded-lg">
                <h4 class="font-semibold text-gray-900 dark:text-white mb-4 flex items-center">
                    <svg class="w-5 h-5 mr-2 text-purple-600" fill="currentColor" viewBox="0 0 20 20">
                        <path fill-rule="evenodd" d="M4 5a2 2 0 00-2 2v8a2 2 0 002 2h12a2 2 0 002-2V7a2 2 0 00-2-2h-1.586a1 1 0 01-.707-.293l-1.121-1.121A2 2 0 0011.172 3H8.828a2 2 0 00-1.414.586L6.293 4.707A1 1 0 015.586 5H4zm6 9a3 3 0 100-6 3 3 0 000 6z" clip-rule="evenodd"></path>
                    </svg>
                    Dati Tecnici Ripresa
                </h4>
                
                <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                        <label class="block mb-2 text-sm font-medium text-gray-900 dark:text-white">Fotografo</label>
                        <input type="text"
                               x-model="metadata.photographer"
                               class="bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 text-gray-900 dark:text-white text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5">
                    </div>
                    <div>
                        <label class="block mb-2 text-sm font-medium text-gray-900 dark:text-white">Data Ripresa</label>
                        <input type="date"
                               x-model="metadata.shoot_date"
                               class="bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 text-gray-900 dark:text-white text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5">
                    </div>
                    <div>
                        <label class="block mb-2 text-sm font-medium text-gray-900 dark:text-white">Fotocamera</label>
                        <input type="text"
                               x-model="metadata.technical_data.camera"
                               class="bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 text-gray-900 dark:text-white text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5"
                               placeholder="Es: Canon EOS 5D">
                    </div>
                    <div>
                        <label class="block mb-2 text-sm font-medium text-gray-900 dark:text-white">Obiettivo</label>
                        <input type="text"
                               x-model="metadata.technical_data.lens"
                               class="bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 text-gray-900 dark:text-white text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5"
                               placeholder="Es: 24-70mm f/2.8">
                    </div>
                </div>
            </div>

            <!-- PAROLE CHIAVE E COPYRIGHT -->
            <div class="bg-gray-50 dark:bg-gray-900 p-4 rounded-lg">
                <h4 class="font-semibold text-gray-900 dark:text-white mb-4 flex items-center">
                    <svg class="w-5 h-5 mr-2 text-indigo-600" fill="currentColor" viewBox="0 0 20 20">
                        <path fill-rule="evenodd" d="M17.707 9.293a1 1 0 010 1.414l-7 7a1 1 0 01-1.414 0l-7-7A.997.997 0 012 10V5a3 3 0 013-3h5c.256 0 .512.098.707.293l7 7zM5 6a1 1 0 100-2 1 1 0 000 2z" clip-rule="evenodd"></path>
                    </svg>
                    Parole Chiave e Diritti
                </h4>
                
                <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div class="md:col-span-2">
                        <label class="block mb-2 text-sm font-medium text-gray-900 dark:text-white">
                            Parole Chiave <span class="text-xs text-gray-500">(separate da virgola)</span>
                        </label>
                        <input type="text"
                               x-model="keywordsString"
                               @input="metadata.keywords = $event.target.value.split(',').map(k => k.trim()).filter(k => k)"
                               class="bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 text-gray-900 dark:text-white text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5"
                               placeholder="Es: ceramica, età del bronzo, scavo">
                    </div>
                    <div>
                        <label class="block mb-2 text-sm font-medium text-gray-900 dark:text-white">Copyright</label>
                        <input type="text"
                               x-model="metadata.copyright"
                               class="bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 text-gray-900 dark:text-white text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5"
                               placeholder="© 2025 Nome Autore">
                    </div>
                    <div>
                        <label class="block mb-2 text-sm font-medium text-gray-900 dark:text-white">Licenza</label>
                        <select x-model="metadata.license"
                                class="bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 text-gray-900 dark:text-white text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5">
                            <option value="">Seleziona...</option>
                            <option value="CC BY">CC BY</option>
                            <option value="CC BY-SA">CC BY-SA</option>
                            <option value="CC BY-NC">CC BY-NC</option>
                            <option value="CC BY-NC-SA">CC BY-NC-SA</option>
                            <option value="Tutti i diritti riservati">Tutti i diritti riservati</option>
                        </select>
                    </div>
                </div>

                <!-- Featured -->
                <div class="mt-4">
                    <label class="flex items-center cursor-pointer">
                        <input type="checkbox"
                               x-model="metadata.featured"
                               class="w-4 h-4 text-blue-600 bg-gray-100 border-gray-300 rounded focus:ring-blue-500 dark:focus:ring-blue-600 dark:ring-offset-gray-800 focus:ring-2 dark:bg-gray-700 dark:border-gray-600">
                        <span class="ml-2 text-sm font-medium text-gray-900 dark:text-gray-300">
                            ⭐ Foto in evidenza
                        </span>
                    </label>
                </div>
            </div>

            <!-- Pulsanti Azione -->
            <div class="flex items-center justify-between pt-6 border-t border-gray-200 dark:border-gray-700">
                <button type="button"
                        @click="closeEditModal()"
                        class="px-6 py-2.5 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 focus:ring-4 focus:ring-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:border-gray-600 dark:hover:bg-gray-700">
                    Annulla
                </button>
                
                <div class="flex gap-3">
                    <button type="button"
                            @click="validateMetadata()"
                            class="px-6 py-2.5 text-sm font-medium text-blue-600 bg-white border border-blue-600 rounded-lg hover:bg-blue-50 focus:ring-4 focus:ring-blue-200">
                        🔍 Valida
                    </button>
                    
                    <button type="submit"
                            :disabled="saving"
                            class="px-6 py-2.5 text-sm font-medium text-white rounded-lg focus:ring-4 focus:ring-blue-300"
                            :class="saving ? 'bg-gray-400 cursor-not-allowed' : 'bg-blue-600 hover:bg-blue-700'">
                        <span x-show="!saving">💾 Salva Metadati</span>
                        <span x-show="saving">⏳ Salvataggio...</span>
                    </button>
                </div>
            </div>
        </form>
    </div>
</div>

<script>
// Inizializzazione metadati con schema JSON
function initPhotoMetadata() {
    return {
        metadata: {
            title: '',
            description: '',
            archaeological_context: '',
            chronology: '',
            subject_type: '',
            stratigraphic_unit: '',
            material: '',
            conservation_state: '',
            photographer: '',
            shoot_date: '',
            location: {
                area: '',
                sector: '',
                coordinates: ''
            },
            technical_data: {
                camera: '',
                lens: '',
                focal_length: null,
                aperture: '',
                iso: null,
                shutter_speed: ''
            },
            keywords: [],
            copyright: '',
            license: '',
            visibility: 'team',
            featured: false
        },
        keywordsString: '',
        saving: false,
        alert: {
            show: false,
            type: 'info',
            message: ''
        },
        
        async loadMetadata(photoId) {
            try {
                const response = await fetch(`/api/photos/${photoId}/metadata`);
                if (response.ok) {
                    const data = await response.json();
                    this.metadata = { ...this.metadata, ...data };
                    this.keywordsString = (this.metadata.keywords || []).join(', ');
                }
            } catch (error) {
                console.error('Errore caricamento metadati:', error);
            }
        },
        
        validateMetadata() {
            const required = ['title', 'description', 'subject_type'];
            const missing = required.filter(field => !this.metadata[field]);
            
            if (missing.length > 0) {
                this.showAlert('warning', `Campi obbligatori mancanti: ${missing.join(', ')}`);
                return false;
            }
            
            this.showAlert('success', '✅ Validazione completata con successo');
            return true;
        },
        
        async saveMetadata() {
            if (!this.validateMetadata()) return;
            
            this.saving = true;
            
            try {
                const response = await fetch(`/api/photos/${selectedPhoto.id}/metadata`, {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${localStorage.getItem('token')}`
                    },
                    body: JSON.stringify(this.metadata)
                });
                
                if (response.ok) {
                    this.showAlert('success', '✅ Metadati salvati con successo!');
                    setTimeout(() => {
                        this.closeEditModal();
                        location.reload();
                    }, 1500);
                } else {
                    throw new Error('Errore salvataggio');
                }
            } catch (error) {
                console.error('Errore:', error);
                this.showAlert('error', '❌ Errore durante il salvataggio');
            } finally {
                this.saving = false;
            }
        },
        
        showAlert(type, message) {
            this.alert = { show: true, type, message };
            setTimeout(() => this.alert.show = false, 5000);
        },
        
        closeEditModal() {
            showEditModal = false;
        }
    };
}
</script>
