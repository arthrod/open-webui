async def process_stream(content: StreamReader):
                sentence = ''
                # Decode and process the chunk
                async for chunk in content.iter_any():
                    # Perform on-the-fly processing of the chunk
                    decoded_chunk = chunk.decode('utf-8')
                    log.info(f"DECODED_CHUNK: {decoded_chunk}")
                    if decoded_chunk.startswith('data: '):
                        try:
                            json_str = decoded_chunk.split('data: ')[1]
                            log.info(f"JSON_STR: {json_str}")
                            

                            # if 'DONE' in json_str:
                            #     yield chunk  
                            
                            data = json.loads(json_str)

                            content = data["choices"][0]["delta"]["content"]
                            # if 'content' in delta:
                            sentence += content
                            
                    

                            # log.info(f'SENTENCE: {sentence}')
                            error = await guard.validate(sentence)
                            log.info(f'validation_passed: {error.validation_passed}')
                            if error.validation_passed is True :
                                log.info(f'SENTENCE valid: {sentence}')
                                yield chunk
                            else:
                                log.error(f"SENTENCE failed: {sentence}")
                                break

                                # log.error(f"Guardrail validation passed: {error}")
                        except Exception as e:
                            log.warning(f"Failed to parse chunk: {e}")
                            yield chunk
                            
                        # except Exception as e:
                        #     log.error(f"ERROR: {e}")
                        #     pass

                        # error = await guard.validate(sentence)
                        # if error.validation_passed is True :
                        #     log.error(f"Guardrail validation passed: {error}")
                        
                        yield chunk