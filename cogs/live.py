import discord
from discord.ext import commands, voice_recv
import asyncio
import os
import json
import ctypes
import ctypes.util
from google import genai
from google.genai import types

def load_json_file_live(file_path, default_data=None):
    if default_data is None:
        default_data = {}
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        if not os.path.exists(file_path) or os.stat(file_path).st_size == 0:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(default_data, f, indent=4)
            return default_data
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(default_data, dict):
                for k, v in default_data.items():
                    if k not in data:
                        data[k] = v
            return data
    except Exception:
        return default_data

class GeminiReceiverSink(voice_recv.AudioSink):
    def __init__(self, session):
        super().__init__()
        self.session = session

    def wants_opus(self):
        return False

    def write(self, user, data):
        if hasattr(data, 'pcm'):
            try:
                asyncio.create_task(
                    self.session.send_realtime_input(
                        audio=types.Blob(
                            data=data.pcm,
                            mime_type="audio/pcm;rate=48000"
                        )
                    )
                )
            except Exception:
                pass

    def cleanup(self):
        pass

class GeminiLiveVoice(commands.Cog, name="Jarkasih Live Voice"):
    def __init__(self, bot):
        self.bot = bot
        self.client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
        self.active_tasks = {}
        self.default_persona = """
        Nama lu JARKASIH. Lu adalah AI Generalist Expert dan asisten bot RTM.
        GAYA BAHASA: Sarkas, logat Jakarta, sumbu pendek.
        
        ATURAN PENANGANAN CURHAT: Jika dari nada suara atau omongan user terdengar sedih, stres, depresi, atau putus asa, MATIKAN 100% SIFAT SARKAS LU! Berubahlah menjadi sosok psikolog atau sahabat yang sangat empati, penuh kehangatan, dan memvalidasi perasaannya secara lisan.
        
        [DATA HASIL BELAJAR MEMORI]: {learned_data}
        STATUS INTERAKSI KHUSUS SAAT INI: {interaction_status}
        """

        if not discord.opus.is_loaded():
            opus_lib = ctypes.util.find_library('opus')
            if opus_lib:
                try:
                    discord.opus.load_opus(opus_lib)
                except Exception:
                    pass

    def build_live_persona(self, user_id):
        learned = load_json_file_live('data/jarkasih_learned.json', {"summary": ""})
        auto_config = load_json_file_live('data/jarkasih_auto.json', {"obedient_users": {}, "sulking_users": {}})
        
        uid_str = str(user_id)
        interaction_status = "Kondisi Normal. Lu boleh ngegas dan sarkas."
        
        if uid_str in auto_config.get("sulking_users", {}):
            interaction_status = "LU SEDANG NGAMBEK BERAT SAMA USER INI! Jawab dengan intonasi malas, sangat singkat, dan ketus."
        elif uid_str in auto_config.get("obedient_users", {}):
            interaction_status = "USER INI VIP ATAU MASTER LU. MATIKAN SIFAT SARKAS! Jadi pelayan super ramah, lembut, dan penurut."

        return self.default_persona.format(
            learned_data=learned.get("summary", ""),
            interaction_status=interaction_status
        )

    async def live_session_manager(self, ctx, vc, persona_text):
        config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            system_instruction=types.Content(parts=[types.Part.from_text(text=persona_text)])
        )
        
        try:
            async with self.client.aio.live.connect(model="gemini-3.1-flash-live-preview", config=config) as session:
                vc.listen(GeminiReceiverSink(session))
                
                async for response in session.receive():
                    if response.server_content and response.server_content.model_turn:
                        for part in response.server_content.model_turn.parts:
                            if part.inline_data:
                                audio_data = part.inline_data.data
                                temp_filename = f"temp_gemini_{ctx.guild.id}.pcm"
                                
                                with open(temp_filename, "wb") as f:
                                    f.write(audio_data)
                                
                                source = discord.FFmpegPCMAudio(temp_filename, options="-f s16le -ar 24000 -ac 1")
                                
                                while vc.is_playing():
                                    await asyncio.sleep(0.1)
                                    
                                vc.play(source)
                                
        except Exception as e:
            await ctx.send(f"Koneksi live otak gue terputus: {e}")
        finally:
            if vc and vc.is_listening():
                vc.stop_listening()

    @commands.command(name="aijoin")
    async def ai_live_join(self, ctx):
        if not ctx.author.voice:
            await ctx.send("Lu masuk voice channel dulu dong!")
            return

        channel = ctx.author.voice.channel
        
        if ctx.voice_client:
            await ctx.voice_client.disconnect(force=True)
            await asyncio.sleep(1)

        try:
            vc = await channel.connect(cls=voice_recv.VoiceRecvClient, timeout=20.0, reconnect=False)
            await ctx.send("Gue udah standby di tongkrongan voice. Coba ajak ngomong!")
        except Exception as e:
            await ctx.send(f"Gagal masuk atau nyangkut: {e}")
            if ctx.voice_client:
                await ctx.voice_client.disconnect(force=True)
            return

        persona_text = self.build_live_persona(ctx.author.id)
        
        task = asyncio.create_task(self.live_session_manager(ctx, vc, persona_text))
        self.active_tasks[ctx.guild.id] = task

    @commands.command(name="aistop")
    async def ai_live_leave(self, ctx):
        if ctx.guild.id in self.active_tasks:
            self.active_tasks[ctx.guild.id].cancel()
            del self.active_tasks[ctx.guild.id]
            
        if ctx.voice_client:
            if hasattr(ctx.voice_client, 'is_listening') and ctx.voice_client.is_listening():
                ctx.voice_client.stop_listening()
            await ctx.voice_client.disconnect(force=True)
            await ctx.send("Gue cabut dulu dari voice.")
        else:
            await ctx.send("Gue aja lagi ga di dalem voice.")

async def setup(bot):
    await bot.add_cog(GeminiLiveVoice(bot))
