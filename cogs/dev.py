import discord
from discord.ext import commands, tasks
import os
import json
import base64
import aiohttp
import asyncio
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions
import re

class IslamicDataUpdater(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.doa_file = 'doa.json'
        self.inspirasi_file = 'inspirasi.json'
        
        self.github_token = os.getenv("ISLAMIC_GITHUB_TOKEN")
        self.github_repo = os.getenv("ISLAMIC_GITHUB_REPO")
        self.github_branch = os.getenv("ISLAMIC_GITHUB_BRANCH", "main")
        
        self.api_keys = []
        if os.getenv("GOOGLE_API_KEY"):
            self.api_keys.append(os.getenv("GOOGLE_API_KEY"))
            
        key_idx = 2
        while True:
            extra_key = os.getenv(f"GOOGLE_API_KEY_{key_idx}")
            if extra_key:
                self.api_keys.append(extra_key)
                key_idx += 1
            else:
                break
                
        self.current_key_idx = 0
        self.configure_genai()
        self.update_loop.start()

    def configure_genai(self):
        if self.api_keys:
            key_to_use = self.api_keys[self.current_key_idx]
            genai.configure(api_key=key_to_use)

    def rotate_api_key(self):
        if len(self.api_keys) > 1:
            self.current_key_idx = (self.current_key_idx + 1) % len(self.api_keys)
            self.configure_genai()
            return True
        return False

    def cog_unload(self):
        self.update_loop.cancel()

    async def push_to_github(self, file_path, content_str):
        if not self.github_token or not self.github_repo:
            return False
            
        url = f"https://api.github.com/repos/{self.github_repo}/contents/{file_path}"
        headers = {
            "Authorization": f"token {self.github_token}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        async with aiohttp.ClientSession() as session:
            sha = None
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    sha = data['sha']
                    
            encoded_content = base64.b64encode(content_str.encode('utf-8')).decode('utf-8')
            payload = {
                "message": f"Data Architect: Update {file_path}",
                "content": encoded_content,
                "branch": self.github_branch
            }
            
            if sha:
                payload["sha"] = sha
                
            async with session.put(url, headers=headers, json=payload) as resp:
                return resp.status in [200, 201]

    def clean_json_response(self, text):
        text = text.strip()
        text = re.sub(r'^```json\s*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'^```\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
        return text.strip()

    async def generate_new_data(self, prompt):
        attempts = max(1, len(self.api_keys))
        for _ in range(attempts):
            try:
                model = genai.GenerativeModel('gemini-2.0-flash-exp')
                response = await model.generate_content_async(prompt)
                raw_text = response.text
                clean_text = self.clean_json_response(raw_text)
                return json.loads(clean_text)
            except google_exceptions.ResourceExhausted:
                if self.rotate_api_key():
                    await asyncio.sleep(1)
                    continue
                break
            except Exception:
                break
        raise Exception("Gagal mengekstrak data dari AI.")

    async def update_inspirasi(self):
        prompt = """
        Anda adalah "Data Architect & Islamic Text Analyst v3.1" tingkat lanjut.
        Tugas: Ekstrak 15 data ayat Al-Quran inspiratif dengan penjelasan yang SANGAT PANJANG, MENDALAM, dan TIDAK HALUSINASI.
        
        ATURAN MUTLAK:
        1. ANTI-HALUSINASI: Ayat, nomor surah, nomor ayat, dan terjemahan HARUS 100% valid dan ada di dalam Al-Quran. Jangan pernah mengarang teks Arab atau terjemahannya.
        2. TEMA ACAK: Pilih ayat dengan variasi tema yang luas seperti cinta kasih, kesabaran ekstrim, adab sosial, pelajaran hidup, kebijaksanaan, humor/keceriaan dalam batasan adab, dan penyembuhan mental.
        3. TAFSIR PANJANG: Key "short_tafsir_id" HARUS berisi penjelasan yang panjang, komprehensif, dan analitis (Minimal 3 sampai 5 kalimat utuh). Jangan berikan tafsir yang terlalu singkat atau dangkal.
        4. PELAJARAN MENDALAM: Key "lesson_id" HARUS berisi refleksi kehidupan yang panjang, filosofis, dan sangat aplikatif untuk kehidupan modern saat ini (Minimal 3 sampai 5 kalimat utuh).
        5. OUTPUT: WAJIB 100% JSON Array murni. Dilarang keras menambahkan teks pengantar, penutup, atau markdown codeblock di luar JSON.

        CONTOH FORMAT OUTPUT YANG DIHARAPKAN:
        [
          {
            "id": "s2a153",
            "surah_id": 2,
            "ayat_id": 153,
            "text_ar": "يَٰٓأَيُّهَا ٱلَّذِينَ ءَامَنُوا۟ ٱسْتَعِينُوا۟ بِٱلصَّبْرِ وَٱلصَّلَوٰةِ ۚ إِنَّ ٱللَّهَ مَعَ ٱلصَّٰبِرِينَ",
            "text_id": "Wahai orang-orang yang beriman! Mohonlah pertolongan (kepada Allah) dengan sabar dan salat. Sungguh, Allah beserta orang-orang yang sabar.",
            "text_en": "O you who have believed, seek help through patience and prayer. Indeed, Allah is with the patient.",
            "short_tafsir_id": "Ayat ini memberikan instruksi psikologis dan spiritual yang sangat kuat bagi manusia dalam menghadapi tekanan hidup yang tak terhindarkan. Allah memformulasikan dua instrumen utama, yakni kesabaran sebagai bentuk pertahanan mental dari dalam diri, dan salat sebagai tali koneksi vertikal untuk memohon intervensi ilahi. Frasa penutupnya memberikan jaminan mutlak bahwa Allah tidak hanya melihat, melainkan secara aktif mendampingi, melindungi, dan memberikan jalan keluar bagi individu-individu yang menolak untuk menyerah dan memilih untuk bersabar.",
            "lesson_id": "Dalam realitas kehidupan modern yang serba cepat dan rentan terhadap stres, ayat ini mengajarkan kita untuk tidak gegabah merespons masalah dengan kepanikan atau amarah. Kesabaran bukanlah sikap pasif menyerah pada keadaan, melainkan sebuah daya tahan aktif untuk tetap berpikir jernih sembari mencari solusi. Dipadukan dengan salat, kita diajarkan untuk meletakkan beban yang berada di luar kendali kita kepada Sang Pencipta, sehingga pikiran menjadi jauh lebih tenang, fokus, dan siap menghadapi tantangan apa pun yang ada di depan mata.",
            "source": "Al-Baqarah (2): 153"
          }
        ]
        """
        
        try:
            new_data = await self.generate_new_data(prompt)
            existing_data = []
            
            if os.path.exists(self.inspirasi_file):
                with open(self.inspirasi_file, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
            
            existing_ids = [item.get('id') for item in existing_data]
            added = 0
            
            for item in new_data:
                if item.get('id') not in existing_ids:
                    existing_data.append(item)
                    added += 1
                    
            if added > 0:
                json_str = json.dumps(existing_data, ensure_ascii=False, indent=2)
                with open(self.inspirasi_file, 'w', encoding='utf-8') as f:
                    f.write(json_str)
                await self.push_to_github(self.inspirasi_file, json_str)
                
            return added
        except Exception:
            return 0

    async def update_doa(self):
        prompt = """
        Anda adalah "Data Architect & Islamic Text Analyst v3.1" tingkat lanjut.
        Tugas: Cari 5 doa Islam dari Al-Quran atau Hadits shahih yang relevan dengan berbagai kondisi kehidupan masa kini.
        
        ATURAN MUTLAK:
        1. ANTI-HALUSINASI: Teks Arab, latin, dan terjemahan harus akurat dan valid berdasarkan sumber literatur Islam yang nyata.
        2. TEMA ACAK: Pilih doa untuk berbagai situasi (penyembuh luka batin, meminta kelancaran rezeki, doa saat merasa jatuh cinta, memohon kesabaran luar biasa, dll).
        3. Teks Arab wajib berharakat lengkap.
        4. OUTPUT: WAJIB 100% JSON Array murni. Dilarang keras menambahkan teks pengantar, penutup, atau markdown.

        CONTOH FORMAT OUTPUT YANG DIHARAPKAN:
        [
          {
            "title_id": "Doa Memohon Ketenangan Batin dan Dilepaskan dari Kesedihan Ekstrem",
            "title_en": "Prayer for Inner Peace and Relief from Extreme Sorrow",
            "arabic": "اللَّهُمَّ إِنِّي أَعُوذُ بِكَ مِنَ الْهَمِّ وَالْحَزَنِ، وَالْعَجْزِ وَالْكَسَلِ، وَالْبُخْلِ وَالْجُبْنِ، وَضَلَعِ الدَّيْنِ وَغَلَبَةِ الرِّجَالِ",
            "latin": "Allahumma inni a'udzu bika minal hammi wal hazani, wal 'ajzi wal kasali, wal bukhli wal jubni, wa dhala'id dayni wa ghalabatir rijaal",
            "translation_id": "Ya Allah, sesungguhnya aku berlindung kepada-Mu dari keluh kesah dan kesedihan, dari kelemahan dan kemalasan, dari sifat bakhil dan penakut, dari lilitan hutang dan penindasan orang-orang.",
            "translation_en": "O Allah, I seek refuge in You from anxiety and sorrow, from weakness and laziness, from miserliness and cowardice, from the burden of debts and from being overpowered by men."
          }
        ]
        """
        
        try:
            new_data = await self.generate_new_data(prompt)
            existing_data = []
            
            if os.path.exists(self.doa_file):
                with open(self.doa_file, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
                    
            existing_titles = [item.get('title_id') for item in existing_data]
            added = 0
            
            for item in new_data:
                if item.get('title_id') not in existing_titles:
                    existing_data.append(item)
                    added += 1
                    
            if added > 0:
                json_str = json.dumps(existing_data, ensure_ascii=False, indent=2)
                with open(self.doa_file, 'w', encoding='utf-8') as f:
                    f.write(json_str)
                await self.push_to_github(self.doa_file, json_str)
                
            return added
        except Exception:
            return 0

    @tasks.loop(hours=1)
    async def update_loop(self):
        await self.update_inspirasi()
        await self.update_doa()

    @update_loop.before_loop
    async def before_update_loop(self):
        await self.bot.wait_until_ready()

    @commands.command(name="islamic_refresh")
    @commands.is_owner()
    async def manual_refresh(self, ctx):
        await ctx.send("Menginisiasi ekstraksi data Islami per jam dengan Algoritma Anti-Halusinasi... Sedang memproses AI.")
        added_i = await self.update_inspirasi()
        added_d = await self.update_doa()
        await ctx.reply(f"Sinkronisasi data selesai Rhdevs. Berhasil memvalidasi dan menambahkan {added_i} Inspirasi panjang & {added_d} Doa ke repositori GitHub.")

async def setup(bot):
    await bot.add_cog(IslamicDataUpdater(bot))
