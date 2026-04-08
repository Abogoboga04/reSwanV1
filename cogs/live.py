import discord
import discord.opus
from discord.ext import commands, voice_recv
import asyncio
import os
import json
import uuid
import traceback
from google import genai
from google.genai import types

original_opus_decode = discord.opus.Decoder.decode

def patched_opus_decode(self, data, *args, **kwargs):
    try:
        return original_opus_decode(self, data, *args, **kwargs)
    except discord.opus.OpusError as e:
        print(f"LOG: Paket diabaikan ({e})", flush=True)
        return b'\x00' * 3840

discord.opus.Decoder.decode = patched_opus_decode

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
    def __init__(self, session, bot_instance, loop):
        super().__init__()
        self.session = session
        self.bot = bot_instance
        self.loop = loop
        self.packet_count = 0
        print("LOG: Sink Telinga Berhasil Dibuat", flush=True)

    def wants_opus(self):
        return False

    def write(self, user, data):
        if user == self.bot.user:
            return
            
        if hasattr(data, 'pcm'):
            self.packet_count += 1
            if self.packet_count % 20 == 0:
                print(f"LOG: Nangkep suara dari {user.name}", flush=True)
            
            try:
                mono_pcm = memoryview(data.pcm).cast('h')[0::2].tobytes()
                coro = self.session.send_realtime_input(
                    audio=types.Blob(
                        data=mono_pcm,
                        mime_type="audio/pcm;rate=48000"
                    )
                )
                asyncio.run_coroutine_threadsafe(coro, self.loop)
            except Exception as e:
                print(f"LOG: Error kirim audio: {e}", flush=True)

    def cleanup(self):
        print("LOG: Telinga Berhenti Mendengar", flush=True)

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
            try:
                discord.opus.load_opus('libopus.so.0')
            except Exception:
                try:
                    discord.opus.load_opus('libopus.so')
                except Exception:
                    pass

    def build_live_persona(self, user_id):
        learned = load_json_file_live('data/jarkasih_learned.json', {"summary": ""})
        auto_config = load_json_file_live('data/jarkasih_auto.json', {"obedient_users": {}, "sulking_users": {}})
        uid_str = str(user_id)
        interaction_status = "Kondisi Normal"
        if uid_str in auto_config.get("sulking_users", {}):
            interaction_status = "LU SEDANG NGAMBEK"
        elif uid_str in auto_config.get("obedient_users", {}):
            interaction_status = "USER INI MASTER LU"
        return self.default_persona.format(learned_data=learned.get("summary", ""), interaction_status=interaction_status)

    async def _playback_task(self, ctx, vc, queue):
        while True:
            file_path = await queue.get()
            if file_path is None:
                break
            try:
                source = discord.FFmpegPCMAudio(file_path, options="-f s16le -ar 24000 -ac 1")
                vc.play(source, after=lambda e, f=file_path: os.remove(f) if os.path.exists(f) else None)
                while vc.is_playing():
                    await asyncio.sleep(0.1)
            except Exception as e:
                print(f"LOG: Error di playback: {e}", flush=True)

    async def _run_session(self, ctx, vc, session):
        print("LOG: Masuk ke loop transmisi", flush=True)
        loop = asyncio.get_running_loop()
        vc.listen(GeminiReceiverSink(session, self.bot, loop))
        
        playback_queue = asyncio.Queue()
        playback_task = asyncio.create_task(self._playback_task(ctx, vc, playback_queue))
        temp_audio_buffer = bytearray()

        try:
            async for response in session.receive():
                if response.server_content:
                    if response.server_content.interrupted:
                        print("LOG: Interupsi suara terdeteksi", flush=True)
                        if vc.is_playing():
                            vc.stop()
                        while not playback_queue.empty():
                            try:
                                old_file = playback_queue.get_nowait()
                                if old_file and os.path.exists(old_file):
                                    os.remove(old_file)
                            except Exception:
                                pass
                        temp_audio_buffer.clear()

                    if response.server_content.model_turn:
                        for part in response.server_content.model_turn.parts:
                            if part.inline_data:
                                temp_audio_buffer.extend(part.inline_data.data)

                    if response.server_content.turn_complete:
                        if len(temp_audio_buffer) > 0:
                            print("LOG: Gemini Merespon dengan suara", flush=True)
                            unique_id = uuid.uuid4().hex
                            file_path = f"temp_gemini_{ctx.guild.id}_{unique_id}.pcm"
                            with open(file_path, "wb") as f:
                                f.write(temp_audio_buffer)
                            temp_audio_buffer.clear()
                            await playback_queue.put(file_path)
        finally:
            await playback_queue.put(None)
            playback_task.cancel()

    async def live_session_manager(self, ctx, vc, persona_text):
        print("LOG: Task Manager Dimulai", flush=True)
        config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            system_instruction=types.Content(parts=[types.Part.from_text(text=persona_text)])
        )
        try:
            print("LOG: Mencoba koneksi ke gemini-3.1-flash-live-preview", flush=True)
            async with self.client.aio.live.connect(model="gemini-3.1-flash-live-preview", config=config) as session:
                await self._run_session(ctx, vc, session)
        except Exception as e:
            print(f"LOG: Gagal di model 3.1: {e}", flush=True)
            try:
                print("LOG: Mencoba koneksi ke gemini-2.5-flash-native-audio-preview-12-2025", flush=True)
                async with self.client.aio.live.connect(model="gemini-2.5-flash-native-audio-preview-12-2025", config=config) as session:
                    await self._run_session(ctx, vc, session)
            except Exception as e2:
                print(f"LOG: Fatal Error di kedua model: {e2}", flush=True)
                traceback.print_exc()
        finally:
            if vc and vc.is_listening():
                vc.stop_listening()

    @commands.command(name="aijoin")
    async def ai_live_join(self, ctx):
        print(f"LOG: Command aijoin dipanggil oleh {ctx.author.name}", flush=True)
        if not ctx.author.voice:
            await ctx.send("Masuk voice dulu bos!")
            return

        channel = ctx.author.voice.channel
        if ctx.voice_client:
            await ctx.voice_client.disconnect(force=True)
            await asyncio.sleep(1)

        try:
            print("LOG: Menjalankan channel.connect...", flush=True)
            vc = await channel.connect(cls=voice_recv.VoiceRecvClient, timeout=20.0, reconnect=False)
            await ctx.send("Gue udah standby. Sapa gue!")
        except Exception as e:
            print(f"LOG: Gagal masuk voice: {e}", flush=True)
            return

        print("LOG: Menyiapkan task manager", flush=True)
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
            await ctx.send("Gue cabut.")

async def setup(bot):
    await bot.add_cog(GeminiLiveVoice(bot))
